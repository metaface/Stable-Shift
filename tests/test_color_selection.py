"""The color-method selector must mean the same thing on both Run paths."""
import json
import os

import numpy as np
from PIL import Image
import pytest

from stable_shift.engine import Options, correct_palette, _palette
from stable_shift import scunet_cleanup
from stable_shift.global_color import color_method_label, METHODS
from tests.test_scunet_reference import palette_scene


def reference_pair():
    source = palette_scene()
    source[155:168, 20:220] = (245, 245, 245)  # bright neutral overlay
    reference = Image.fromarray(np.uint8(source[:, ::-1].astype(float)*[.8, .5, .3]+.5))
    return source, reference


@pytest.mark.parametrize('method,applied', [('Classic', 'Classic'),
    ('Robust global', 'Classic'), ('Global palette', 'Global palette')])
def test_normal_and_scunet_honor_the_same_requested_method(method, applied, monkeypatch):
    source, reference = reference_pair()
    monkeypatch.setattr(scunet_cleanup, 'denoise', lambda rgb, progress: (rgb.copy(), {'device_name': 'Test stub'}))
    opts = Options(color_method=method, blotch_strength=100)
    normal, normal_report = correct_palette(reference, source, source, opts)
    preview = scunet_cleanup.prepare_scunet_cleanup(reference, Image.fromarray(source), opts)
    out, live_report = preview.render(0)
    np.testing.assert_array_equal(out, normal)
    for report in (normal_report, live_report['color_correction']):
        assert report['requested_method'] == method
        assert report['selected_method'] == applied
        if method != applied:
            assert report['fallback_from'] == method and report['fallback_reason']
            assert color_method_label(report) == 'Robust global -> Classic (fallback)'
        else:
            assert color_method_label(report) == method


@pytest.mark.parametrize('broad', [0, 100])
def test_classic_retains_the_original_run_pixels(broad):
    source, reference = reference_pair()
    result, report = correct_palette(reference, source, source,
        Options(color_method='Classic', blotch_strength=broad))
    np.testing.assert_array_equal(result, _palette(reference, source))
    assert report['selected_method'] == 'Classic'


def test_reference_off_does_not_apply_any_selected_method():
    source, reference = reference_pair()
    for method in METHODS:
        out, report = correct_palette(reference, source, source,
            Options(color_method=method, color_match=False))
        np.testing.assert_array_equal(out, source)
        assert report['requested_method'] == method
        assert color_method_label(report) == 'Off'


@pytest.mark.skipif(os.name != 'nt' and not os.environ.get('DISPLAY'), reason='Tk needs a display')
def test_live_color_switches_reuse_scunet_and_save_requested_and_applied_methods(tmp_path, monkeypatch):
    from stable_shift.app import filedialog, messagebox
    from tests.test_ui import make_app, close_app
    from tests.test_scunet_ui import finish
    root, app = make_app()
    try:
        source, reference = reference_pair()
        source_path, ref_path = tmp_path/'edited.png', tmp_path/'reference.png'
        Image.fromarray(source).save(source_path)
        reference.save(ref_path)
        app.set_image('edited', source_path)
        app.set_image('clean', ref_path)
        calls = []
        def model(rgb, progress):
            calls.append(True)
            return rgb.copy(), {'device_name': 'Test stub'}
        monkeypatch.setattr(scunet_cleanup, 'denoise', model)
        for key in ('showerror', 'showwarning'):
            monkeypatch.setattr(messagebox, key, lambda *a: pytest.fail(str(a)))
        outputs = {}
        for method in METHODS:
            app.color_method.set(method)
            app.prepare_scunet_cleanup()
            finish(root, app)
            report = app.maps['report']['color_correction']
            assert report['requested_method'] == method
            assert color_method_label(report) in app.result_info.get()
            outputs[method] = np.array(app.result)
            if method == 'Robust global':
                assert 'Classic (fallback)' in app.result_info.get()
                path = tmp_path/'fallback.png'
                monkeypatch.setattr(filedialog, 'asksaveasfilename', lambda **k: str(path))
                app.save()
                saved = json.loads(path.with_suffix('.settings.json').read_text())
                assert saved['color_correction']['requested_method'] == 'Robust global'
                assert saved['color_correction']['selected_method'] == 'Classic'
        assert len(calls) == 1
        assert np.abs(outputs['Classic'].astype(float)-outputs['Global palette']).mean() > 1
        # Normal Run must also identify a fallback before the long timing text.
        app.queue.put(('result', (Image.fromarray(source), {'report': {
            'backend': 'Color stage', 'options': {'antialias_strength': 0},
            'color_correction': {'requested_method': 'Robust global',
                                 'selected_method': 'Classic'}}})))
        app.poll()
        assert app.result_info.get().startswith('Color stage | Color: Robust global -> Classic (fallback)')
    finally:
        close_app(root)
