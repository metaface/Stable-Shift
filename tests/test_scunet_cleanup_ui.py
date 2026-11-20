"""Exercise the real Tk worker, cached slider, save and stale-result handling."""
import json
import os

import numpy as np
from PIL import Image
import pytest

from stable_shift import scunet_cleanup
from tests.test_scunet_cleanup import scene
from tests.test_scunet_ui import finish
from tests.test_ui import make_app, close_app

pytestmark = pytest.mark.skipif(os.name != 'nt' and not os.environ.get('DISPLAY'), reason='Tk UI needs a display')


def load_source(app, tmp_path):
    path = tmp_path/'source.png'
    Image.fromarray(scene()[0]).save(path)
    app.set_image('edited', path)
    app.palette.set(False)


def test_ui_cleanup_uses_one_model_pass_live_blends_and_saves_the_displayed_setting(tmp_path, monkeypatch):
    from stable_shift.app import filedialog, messagebox
    root, app = make_app()
    try:
        for key in ('showerror', 'showwarning'):
            monkeypatch.setattr(messagebox, key, lambda *a: pytest.fail(str(a)))
        load_source(app, tmp_path)
        app.method.set('CPU BM3D')
        app.strokes_enabled.set(True)
        app.aa_enabled.set(True)
        calls = []
        def model(rgb, progress):
            calls.append(True)
            return rgb.copy(), {'device_name': 'Test stub', 'seconds': .1}
        monkeypatch.setattr(scunet_cleanup, 'denoise', model)
        app.prepare_scunet_cleanup()
        finish(root, app)
        assert app.live_strength_label.get() == 'SCUNet cleanup %:'
        assert 'model only' in app.live_help.get()
        assert app.maps['report']['scunet_cleanup']['strength'] == 100
        assert 'line_preservation' not in app.maps['report']
        for strength in (0, 200, 100, 135):
            app.line_strength.set(strength)
            app.render_live_lines()
            np.testing.assert_array_equal(app.result, app.line_preview.render(strength)[0])
        assert len(calls) == 1
        displayed = np.array(app.result)
        # Save from the displayed report while the slider still has a pending edit.
        app.line_strength.set(200)
        monkeypatch.setattr(filedialog, 'askdirectory', lambda **k: str(tmp_path))
        app.save_live_lines()
        directory, = tmp_path.glob('scunet_cleanup_v223_*')
        saved = json.loads((directory/'scunet_cleanup_settings.json').read_text())
        assert saved['scunet_cleanup']['strength'] == 135
        np.testing.assert_array_equal(Image.open(directory/'03_selected.png'), displayed)
        assert (directory/'share_scunet_cleanup.zip').is_file()
        # Ordinary image save must also use the displayed strength.
        path = tmp_path/'displayed.png'
        monkeypatch.setattr(filedialog, 'asksaveasfilename', lambda **k: str(path))
        app.save()
        assert json.loads(path.with_suffix('.settings.json').read_text())['scunet_cleanup']['strength'] == 135
        np.testing.assert_array_equal(Image.open(path), displayed)
        app.line_strength.set(100)
        app.render_live_lines()
        app.prepare_scunet_cleanup()
        finish(root, app)
        assert len(calls) == 1 and app.maps['report']['model_output_reused']
    finally:
        close_app(root)


def test_failed_cleanup_and_stale_worker_retain_the_previous_result(tmp_path, monkeypatch):
    from stable_shift.app import messagebox
    root, app = make_app()
    try:
        load_source(app, tmp_path)
        retained = Image.new('RGB', (17, 13), 'blue')
        app.result = retained
        errors = []
        monkeypatch.setattr(messagebox, 'showerror', lambda *a: errors.append(a))
        def fail(*a, **k):
            raise RuntimeError('model unavailable')
        monkeypatch.setattr(scunet_cleanup, 'prepare_scunet_cleanup', fail)
        app.prepare_scunet_cleanup()
        finish(root, app)
        assert app.result is retained and errors and app.line_preview is None
        app.busy = True
        app.queue.put(('live_scunet_ready', (app._line_generation-1, object())))
        app.queue.put(('live_scunet_error', (app._line_generation-1, 'stale', 'stale')))
        app.poll()
        assert app.busy and app.result is retained and len(errors) == 1
        # A busy click cannot start an overlapping preparation.
        app.prepare_scunet_cleanup()
        assert app.busy
    finally:
        close_app(root)


def test_switching_back_to_line_preview_restores_its_label_and_report(tmp_path, monkeypatch):
    from stable_shift import live_lines
    from tests.test_live_lines import preview
    root, app = make_app()
    try:
        load_source(app, tmp_path)
        monkeypatch.setattr(scunet_cleanup, 'denoise', lambda rgb, progress: (rgb.copy(), {'device_name': 'Test stub'}))
        app.prepare_scunet_cleanup()
        finish(root, app)
        monkeypatch.setattr(live_lines, 'prepare_line_preview', lambda *a: preview())
        app.prepare_live_lines()
        finish(root, app)
        assert app.live_strength_label.get() == 'Line reconstruction %:'
        assert 'line_preservation' in app.maps['report'] and 'scunet_cleanup' not in app.maps['report']
    finally:
        close_app(root)


def test_cleanup_cache_cannot_be_used_as_the_classical_scunet_comparison_control(tmp_path, monkeypatch):
    from stable_shift import scunet_comparison
    from stable_shift.app import filedialog
    root, app = make_app()
    try:
        load_source(app, tmp_path)
        monkeypatch.setattr(scunet_cleanup, 'denoise', lambda rgb, progress: (rgb.copy(), {'device_name': 'Test stub'}))
        app.prepare_scunet_cleanup()
        finish(root, app)
        retained = app.result
        cached_controls = []
        def export(*args, **kwargs):
            cached_controls.append(kwargs['current_preview'])
            return {'share_zip': 'test.zip', 'scunet': {'device_name': 'Test stub', 'seconds': .1}}
        monkeypatch.setattr(scunet_comparison, 'export_scunet_comparison', export)
        monkeypatch.setattr(filedialog, 'askdirectory', lambda **k: str(tmp_path))
        app.compare_scunet()
        finish(root, app)
        assert cached_controls == [None]
        assert app.result is retained
    finally:
        close_app(root)
