"""Real Tk/tkdnd integration checks; run under a display or on Windows."""
import os
from pathlib import Path
import time

from PIL import Image
import pytest

pytestmark = pytest.mark.skipif(os.name != 'nt' and not os.environ.get('DISPLAY'), reason='Tk UI needs a display')


def make_app():
    from tkinterdnd2 import TkinterDnD
    from stable_shift.app import App
    root = TkinterDnD.Tk()
    app = App(root, dnd_available=True)
    root.update()
    return root, app


def close_app(root):
    for callback in root.tk.call('after', 'info'):
        root.after_cancel(callback)
    root.destroy()


def native_drop(root, app, key, path):
    # Exercise the actual registered Tcl callback and its native DnD argument
    # conversion, rather than bypassing the binding with a direct Python call.
    canvas = app.canvases[key]
    callback = canvas.dnd_bind('<<Drop>>').split()[0]
    payload = root.tk.call('list', str(path))
    args = ['copy', 'copy', '1', 'DND_Files', 'DND_Files', 'DND_Files', 'DND_Files',
            payload, '<<Drop>>', 'DND_Files', '', 'DND_Files', 'DND_Files',
            'DND_Files', 'DND_Files', str(canvas), '20', '20']
    return root.tk.call(callback, *args)


def test_native_drop_slots_theme_and_busy_guard(tmp_path):
    from tkinterdnd2 import REFUSE_DROP, COPY
    root, app = make_app()
    try:
        clean = tmp_path / 'clean {palette} café.png'
        edited = tmp_path / 'edited image with spaces.png'
        Image.new('RGB', (37, 29), 'blue').save(clean)
        Image.new('RGB', (81, 73), 'green').save(edited)
        assert native_drop(root, app, 'clean', clean) == COPY
        assert app.images['clean'].size == (37, 29)
        assert app.images['edited'] is None
        assert native_drop(root, app, 'edited', edited) == COPY
        assert app.images['edited'].size == (81, 73)
        app.busy = True
        assert native_drop(root, app, 'clean', edited) == REFUSE_DROP
        assert app.images['clean'].size == (37, 29)
        app.busy = False
        for theme, expected in [('Dark', '#151719'), ('Light', '#dfe3e8')]:
            app.theme.set(theme)
            app.apply_theme()
            root.update()
            assert app.canvases['edited'].cget('background') == expected
    finally:
        close_app(root)


def test_ui_worker_save_and_actual_run_settings(tmp_path, monkeypatch):
    import json
    import numpy as np
    from stable_shift.app import filedialog, messagebox
    root, app = make_app()
    try:
        def fail(*args, **kwargs):
            pytest.fail('Unexpected UI error: '+str(args))
        monkeypatch.setattr(messagebox, 'showerror', fail)
        monkeypatch.setattr(messagebox, 'showwarning', fail)
        rng = np.random.default_rng(5)
        path = tmp_path / 'input image.png'
        Image.fromarray(np.uint8(rng.integers(80, 105, (80, 96, 3)))).save(path)
        assert app.set_image('edited', path)
        app.palette.set(False)
        app.method.set('Region cleanup only')
        app.cleanup.set(75)
        app.run()
        deadline = time.monotonic()+15
        while app.busy and time.monotonic() < deadline:
            root.update()
            time.sleep(.01)
        assert not app.busy
        assert app.result.size == (96, 80)
        assert app.maps['report']['options']['cleanup'] == 75
        app.cleanup.set(20)  # Saving must describe the run, not changed controls.
        output = tmp_path / 'result.png'
        monkeypatch.setattr(filedialog, 'asksaveasfilename', lambda **kwargs: str(output))
        app.save()
        assert output.exists()
        saved = json.loads(output.with_suffix('.settings.json').read_text())
        assert saved['options']['cleanup'] == 75
        maps_folder = tmp_path / 'maps'
        maps_folder.mkdir()
        monkeypatch.setattr(filedialog, 'askdirectory', lambda **kwargs: str(maps_folder))
        app.save_maps()
        assert (maps_folder / 'diagnostics_raw.npz').exists()
        assert (maps_folder / 'source_line_core.png').exists()
        assert (maps_folder / 'MAP_LEGEND.md').exists()
        assert app.set_image('edited', path)
        assert app.result is None  # No stale output after replacing an input.
    finally:
        close_app(root)


def test_ui_legacy_manual_comparison_worker(tmp_path, monkeypatch):
    import json
    from stable_shift.app import filedialog, messagebox
    root, app = make_app()
    try:
        def fail(*args, **kwargs):
            pytest.fail('Unexpected UI error: '+str(args))
        monkeypatch.setattr(messagebox, 'showerror', fail)
        monkeypatch.setattr(messagebox, 'showwarning', fail)
        reference = tmp_path/'reference.png'
        edited = tmp_path/'edited.png'
        Image.new('RGB', (32, 24), (110, 140, 170)).save(reference)
        Image.new('RGB', (96, 80), (80, 100, 120)).save(edited)
        app.set_image('clean', reference)
        app.set_image('edited', edited)
        app.method.set('Region cleanup only')
        app.cleanup.set(70)
        app.blotch_strength.set(100)
        monkeypatch.setattr(filedialog, 'askdirectory', lambda **kwargs: str(tmp_path))
        app.compare()
        deadline = time.monotonic()+15
        while app.busy and time.monotonic() < deadline:
            root.update()
            time.sleep(.01)
        assert not app.busy
        folder, = tmp_path.glob('stable_shift_v2_*')
        assert (folder/'01_color_only.png').exists()
        assert (folder/'02_surface_only.png').exists()
        saved = json.loads((folder/'settings_and_timings.json').read_text())
        assert all(run['options']['auto_strength'] is False for run in saved['runs'])
        assert all(run['options']['blotch_strength'] == 0 for run in saved['runs'])
        assert 'Comparison saved:' in app.status.get()
    finally:
        close_app(root)


def test_ui_compare_auto_button_exports_both_variants_and_share_archive(tmp_path, monkeypatch):
    import json
    from stable_shift.app import filedialog, messagebox
    from tests.test_faint_lines import faint_stroke
    root, app = make_app()
    try:
        def fail(*args, **kwargs):
            pytest.fail('Unexpected UI error: '+str(args))
        monkeypatch.setattr(messagebox, 'showerror', fail)
        monkeypatch.setattr(messagebox, 'showwarning', fail)
        path = tmp_path/'faint source.png'
        Image.fromarray(faint_stroke()[0]).save(path)
        app.set_image('clean', path)
        app.set_image('edited', path)
        assert app.automatic.get() is True
        assert app.opts().faint_continuity is False
        app.method.set('Region cleanup only')
        app.cleanup.set(100)
        app.blotch_strength.set(100)
        monkeypatch.setattr(filedialog, 'askdirectory', lambda **kwargs: str(tmp_path))
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        button = next(w for w in descendants(root) if w.winfo_class() == 'TButton' and w.cget('text') == 'Compare auto')
        button.invoke()
        deadline = time.monotonic()+15
        while app.busy and time.monotonic() < deadline:
            root.update()
            time.sleep(.01)
        assert not app.busy
        folder, = tmp_path.glob('auto_test_v28_*')
        saved = json.loads((folder/'auto_settings_and_timings.json').read_text())
        assert saved['manual']['options']['auto_strength'] is False
        assert saved['automatic']['options']['auto_strength'] is True
        assert saved['manual']['options']['faint_continuity'] is False
        assert saved['automatic']['options']['faint_continuity'] is False
        assert saved['source_protection_check']['changed_after_palette'] == 0
        assert (folder/'share_auto_test.zip').exists()
        assert (folder/'03_auto_same_palette.png').exists()
        assert 'Auto:' in app.result_info.get()
    finally:
        close_app(root)


def test_ui_aa_preview_reuses_last_run_and_clears_with_input(tmp_path, monkeypatch):
    import numpy as np
    from stable_shift import engine
    from stable_shift.app import messagebox
    from tests.test_finishing import colors
    root, app = make_app()
    try:
        def fail(*args, **kwargs):
            pytest.fail('Unexpected UI error: '+str(args))
        monkeypatch.setattr(messagebox, 'showerror', fail)
        monkeypatch.setattr(messagebox, 'showwarning', fail)
        calls = []
        def backend(rgb, *args):
            calls.append(args)
            return rgb.copy()
        monkeypatch.setattr(engine, '_bm3d', backend)
        path = tmp_path/'image.png'
        Image.fromarray(colors()).save(path)
        app.set_image('edited', path)
        app.palette.set(False)
        assert app.color_method.get() == 'Classic'
        assert not app.aa_enabled.get()
        app.method.set('CPU BM3D')
        app.automatic.set(False)
        app.cleanup.set(0)
        app.blotch_strength.set(0)
        def finish():
            deadline = time.monotonic()+15
            while app.busy and time.monotonic() < deadline:
                root.update()
                time.sleep(.01)
            assert not app.busy
        app.run()
        finish()
        original = np.asarray(app.result).copy()
        assert len(calls) == 1
        app.cleanup.set(100)
        app.color_method.set('Robust global')
        app.aa_enabled.set(True)
        app.aa_strength.set(60)
        app.preview_antialias()
        finish()
        assert len(calls) == 1
        assert app.maps['report']['options']['cleanup'] == 0
        assert app.maps['report']['options']['color_method'] == 'Classic'
        assert app.maps['report']['options']['antialias_strength'] == 60
        assert np.any(np.asarray(app.result) != original)
        app.aa_enabled.set(False)
        app.preview_antialias()
        finish()
        assert np.array_equal(np.asarray(app.result), original)
        app.set_image('edited', path)
        assert app.pre_antialias is None
    finally:
        close_app(root)


def test_ui_color_comparison_exports_one_fixed_cleanup(tmp_path, monkeypatch):
    import json
    from stable_shift.app import filedialog, messagebox
    from tests.test_finishing import colors, shifted
    root, app = make_app()
    try:
        def fail(*args, **kwargs):
            pytest.fail('Unexpected UI error: '+str(args))
        monkeypatch.setattr(messagebox, 'showerror', fail)
        monkeypatch.setattr(messagebox, 'showwarning', fail)
        rgb = colors()
        source, reference = tmp_path/'source.png', tmp_path/'ref.png'
        Image.fromarray(rgb).save(source)
        Image.fromarray(shifted(rgb)).save(reference)
        app.set_image('edited', source)
        app.set_image('clean', reference)
        app.method.set('Region cleanup only')
        app.aa_enabled.set(True)
        monkeypatch.setattr(filedialog, 'askdirectory', lambda **kwargs: str(tmp_path))
        app.compare_colors()
        deadline = time.monotonic()+15
        while app.busy and time.monotonic() < deadline:
            root.update()
            time.sleep(.01)
        assert not app.busy
        folder, = tmp_path.glob('color_test_v29_*')
        assert (folder/'share_color_test.zip').exists()
        saved = json.loads((folder/'color_settings_and_timings.json').read_text())
        assert saved['cleanup_run']['options']['antialias_strength'] == 0
        assert saved['requested_options']['antialias_strength'] == 35
        assert 'Color comparison saved:' in app.status.get()
    finally:
        close_app(root)


def test_ui_stroke_preview_has_full_power_and_reuses_fixed_color_pixels(tmp_path, monkeypatch):
    import numpy as np
    from stable_shift import engine
    from stable_shift.app import messagebox
    from tests.test_stroke_cleanup import strokes
    root, app = make_app()
    try:
        def fail(*args, **kwargs):
            pytest.fail('Unexpected UI error: '+str(args))
        monkeypatch.setattr(messagebox, 'showerror', fail)
        monkeypatch.setattr(messagebox, 'showwarning', fail)
        calls = []
        def backend(rgb, *args):
            calls.append(args)
            return rgb.copy()
        monkeypatch.setattr(engine, '_bm3d', backend)
        path = tmp_path/'colored strokes.png'
        Image.fromarray(strokes()[1]).save(path)
        app.set_image('edited', path)
        app.palette.set(False)
        app.method.set('CPU BM3D')
        app.automatic.set(False)
        app.cleanup.set(0)
        app.blotch_strength.set(0)
        assert not app.strokes_enabled.get()
        assert app.stroke_strength.get() == 100
        def finish():
            deadline = time.monotonic()+15
            while app.busy and time.monotonic() < deadline:
                root.update()
                time.sleep(.01)
            assert not app.busy
        app.run()
        finish()
        original = np.asarray(app.result).copy()
        app.strokes_enabled.set(True)
        app.noise.set(0)  # Preview must retain the settings actually run.
        app.preview_strokes()
        finish()
        full = np.asarray(app.result).copy()
        assert len(calls) == 1
        assert np.any(full != original)
        assert app.maps['report']['options']['noise'] == 100
        assert app.maps['report']['options']['stroke_strength'] == 100
        app.preview_strokes()
        finish()
        assert np.array_equal(np.asarray(app.result), full)
        app.aa_enabled.set(True)
        app.preview_antialias()
        finish()
        assert app.maps['report']['options']['stroke_strength'] == 100
        assert np.array_equal(app.post_color, original)
        app.strokes_enabled.set(False)
        app.aa_enabled.set(False)
        app.preview_strokes()
        finish()
        assert np.array_equal(np.asarray(app.result), original)
        assert len(calls) == 1
        app.set_image('edited', path)
        assert app.post_color is None and app.pre_antialias is None
    finally:
        close_app(root)


def test_ui_stroke_comparison_exports_0_60_100_with_aa_off(tmp_path, monkeypatch):
    import json
    from stable_shift.app import filedialog, messagebox
    from tests.test_stroke_cleanup import strokes
    root, app = make_app()
    try:
        def fail(*args, **kwargs):
            pytest.fail('Unexpected UI error: '+str(args))
        monkeypatch.setattr(messagebox, 'showerror', fail)
        monkeypatch.setattr(messagebox, 'showwarning', fail)
        path = tmp_path/'stitches.png'
        Image.fromarray(strokes()[1]).save(path)
        app.set_image('edited', path)
        app.palette.set(False)
        app.method.set('Region cleanup only')
        app.strokes_enabled.set(True)
        app.stroke_strength.set(20)
        app.aa_enabled.set(True)
        monkeypatch.setattr(filedialog, 'askdirectory', lambda **kwargs: str(tmp_path))
        app.compare_strokes()
        deadline = time.monotonic()+15
        while app.busy and time.monotonic() < deadline:
            root.update()
            time.sleep(.01)
        assert not app.busy
        folder, = tmp_path.glob('stroke_test_v210_*')
        saved = json.loads((folder/'stroke_settings_and_timings.json').read_text())
        assert [run['strength'] for run in saved['runs']] == [0, 60, 100]
        assert all(run['antialias_strength'] == 0 for run in saved['runs'])
        assert saved['upstream_run']['options']['stroke_strength'] == 0
        assert saved['requested_options']['stroke_strength'] == 20
        assert (folder/'share_stroke_test.zip').exists()
    finally:
        close_app(root)
