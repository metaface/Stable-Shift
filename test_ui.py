"""Real Tk/tkdnd integration checks; run under a display or on Windows."""
import os
from pathlib import Path
import time

from PIL import Image
import pytest

pytestmark = pytest.mark.skipif(os.name != 'nt' and not os.environ.get('DISPLAY'), reason='Tk UI needs a display')


def make_app():
    from tkinterdnd2 import TkinterDnD
    from app import App
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
    from app import filedialog, messagebox
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
