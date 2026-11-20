from dataclasses import asdict, replace
import json
from zipfile import ZipFile

import numpy as np
from PIL import Image
import pytest

from stable_shift.engine import Options
from stable_shift.global_color import GlobalColor
from stable_shift.live_lines import LinePreview, image_signature
from stable_shift import scunet_comparison as comparison


def fixture(color=True):
    source = Image.fromarray(np.random.default_rng(14).integers(20, 180, (60, 75, 3), dtype=np.uint8))
    reference = Image.fromarray(255-np.asarray(source))
    options = Options(color_match=color, noise=12, color_noise=7, auto_strength=True,
                      cleanup=100, blotch_strength=100, source_guard=True,
                      antialias_strength=100, stroke_strength=100)
    transform = GlobalColor(np.diag([.8, .9, 1.]), np.zeros(3), np.full(3, .05))
    report = {'selected_method': 'Off'} if not color else {
        'selected_method': 'Robust global', 'matrix': transform.matrix.tolist(),
        'source_pivot': transform.source_pivot.tolist(), 'reference_pivot': transform.reference_pivot.tolist()}
    base = np.full((60, 75, 3), 100, np.uint8)
    preview = LinePreview(base, base+10, base+20, np.ones((60, 75), bool), {
        'requested_options': asdict(options), 'color_correction': report,
        'input_signatures': {'edited': image_signature(source), 'reference': image_signature(reference)}})
    model = np.full_like(base, (20, 45, 70))
    return source, reference, options, preview, model, transform


@pytest.mark.parametrize('color', [False, True])
@pytest.mark.parametrize('strength', [0, 100, 200])
def test_comparison_uses_full_model_and_exact_current_color_coefficients(tmp_path, monkeypatch, color, strength):
    source, reference, opts, preview, model, transform = fixture(color)
    calls = []
    def predict(rgb, progress):
        np.testing.assert_array_equal(rgb, source)
        calls.append('model')
        return model.copy(), {'device_name': 'CPU', 'seconds': 1}
    def prepare(ref, edit, options, progress):
        calls.append('current')
        assert options == opts
        return preview
    monkeypatch.setattr(comparison, 'denoise', predict)
    monkeypatch.setattr(comparison, 'prepare_line_preview', prepare)
    report = comparison.export_scunet_comparison(reference, source, opts, tmp_path, line_strength=strength)
    assert calls == ['model', 'current']
    expected = transform.apply(model) if color else model
    np.testing.assert_array_equal(Image.open(tmp_path/'02_scunet_only.png'), expected)
    np.testing.assert_array_equal(Image.open(tmp_path/'scunet_before_color.png'), model)
    np.testing.assert_array_equal(Image.open(tmp_path/'01_current_pipeline.png'), preview.render(strength)[0])
    assert report['scunet_only']['model_strength_percent'] == 100
    assert not any(report['scunet_only'][key] for key in (
        'automatic_limits', 'source_copyback', 'local_cleanup', 'broad_cleanup', 'pyramid', 'stroke_fitting', 'antialias'))
    assert report['color_correction'] == preview.report['color_correction']
    saved = json.loads((tmp_path/'scunet_settings_and_timings.json').read_text())
    assert saved['requested_options'] == asdict(opts)
    assert saved['current_line_strength'] == strength
    with ZipFile(tmp_path/report['share_zip']) as archive:
        assert {'02_scunet_only.png', 'scunet_before_color.png', 'edited_source.png',
                '01_current_pipeline.png', 'scunet_settings_and_timings.json'} <= set(archive.namelist())


def test_valid_cached_current_does_not_rerun_accepted_pipeline(tmp_path, monkeypatch):
    source, ref, opts, preview, model, _ = fixture()
    monkeypatch.setattr(comparison, 'denoise', lambda *a: (model, {}))
    monkeypatch.setattr(comparison, 'prepare_line_preview', lambda *a: pytest.fail('Must reuse current preparation'))
    report = comparison.export_scunet_comparison(ref, source, opts, tmp_path, current_preview=preview)
    assert report['current_preparation_reused']


@pytest.mark.parametrize('change', ['options', 'edited', 'reference'])
def test_wrong_cached_inputs_are_rejected_before_model_run(tmp_path, monkeypatch, change):
    source, ref, opts, preview, model, _ = fixture()
    if change == 'options':
        opts = replace(opts, cleanup=50)
    else:
        altered = np.asarray(source if change == 'edited' else ref).copy()
        altered[0, 0, 0] += 1
        if change == 'edited':
            source = Image.fromarray(altered)
        else:
            ref = Image.fromarray(altered)
    monkeypatch.setattr(comparison, 'denoise', lambda *a: pytest.fail('Wrong cache must fail before model'))
    with pytest.raises(ValueError, match='cached current pipeline'):
        comparison.export_scunet_comparison(ref, source, opts, tmp_path, current_preview=preview)


def test_model_error_does_not_run_current_pipeline(tmp_path, monkeypatch):
    source, ref, opts, *_ = fixture()
    def failed(*a):
        raise RuntimeError('SCUNet unavailable')
    monkeypatch.setattr(comparison, 'denoise', failed)
    monkeypatch.setattr(comparison, 'prepare_line_preview', lambda *a: pytest.fail('Must fail before classical preparation'))
    with pytest.raises(RuntimeError, match='unavailable'):
        comparison.export_scunet_comparison(ref, source, opts, tmp_path)


def test_identity_color_report_reconstructs_exact_identity():
    model = comparison.color_transform({'selected_method': 'Robust global',
        'reason': 'Identical reference and baseline; identity transform.'})
    source = np.random.default_rng(1).integers(0, 256, (5, 9, 3), dtype=np.uint8)
    np.testing.assert_array_equal(model.apply(source), source)


def test_incompatible_color_field_is_rejected():
    with pytest.raises(ValueError, match='uniform RGB'):
        comparison.color_transform({'selected_method': 'Classic'})


def test_share_budget_retains_compared_results_and_inputs_before_extra_controls(tmp_path, monkeypatch):
    source, ref, opts, preview, model, _ = fixture()
    monkeypatch.setattr(comparison, 'denoise', lambda *a: (model, {}))
    report = comparison.export_scunet_comparison(ref, source, opts, tmp_path, current_preview=preview)
    required = report['share_required_files']
    size = sum((tmp_path/name).stat().st_size for name in required)
    size += (tmp_path/'scunet_before_color.png').stat().st_size
    size += (tmp_path/'scunet_settings_and_timings.json').stat().st_size+200_500
    monkeypatch.setattr(comparison, 'SHARE_LIMIT', size)
    saved = comparison.save_bundle(tmp_path, report, sorted(p.name for p in tmp_path.glob('crop_*.png')))
    assert saved['share_zip']
    assert '03_input_same_colors.png' in saved['omitted_optional_files']
    assert (tmp_path/'03_input_same_colors.png').is_file()
    with ZipFile(tmp_path/saved['share_zip']) as archive:
        assert set(required) <= set(archive.namelist())
        assert '03_input_same_colors.png' not in archive.namelist()
    assert (tmp_path/saved['share_zip']).stat().st_size <= size
