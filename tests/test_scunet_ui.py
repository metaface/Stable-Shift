import os
from pathlib import Path
from types import SimpleNamespace
import time

import numpy as np
from PIL import Image
import pytest

from tests.test_ui import make_app, close_app

pytestmark = pytest.mark.skipif(os.name != 'nt' and not os.environ.get('DISPLAY'), reason='Tk UI needs a display')


def finish(root, app):
    deadline = time.monotonic()+15
    while app.busy and time.monotonic() < deadline:
        root.update()
        time.sleep(.01)
    assert not app.busy


def test_ui_scunet_comparison_exports_model_only_and_keeps_current_result(tmp_path, monkeypatch):
    import json
    from stable_shift.app import filedialog, messagebox
    from stable_shift import scunet_comparison
    from tests.test_finishing import colors
    root, app = make_app()
    try:
        for key in ('showerror', 'showwarning'):
            monkeypatch.setattr(messagebox, key, lambda *a: pytest.fail(str(a)))
        path = tmp_path/'source.png'
        source = colors()
        Image.fromarray(source).save(path)
        app.set_image('edited', path)
        app.palette.set(False)
        app.method.set('Region cleanup only')
        app.line_strength.set(175)
        retained = Image.new('RGB', (7, 9), 'red')
        app.result = retained
        calls = []
        model = np.full_like(source, (20, 50, 80))
        def denoise(rgb, progress):
            calls.append(rgb.copy())
            return model.copy(), {'device_name': 'CPU', 'seconds': .1}
        monkeypatch.setattr(scunet_comparison, 'denoise', denoise)
        monkeypatch.setattr(filedialog, 'askdirectory', lambda **k: str(tmp_path))
        app.compare_scunet()
        finish(root, app)
        directory, = tmp_path.glob('scunet_test_v220_*')
        np.testing.assert_array_equal(Image.open(directory/'02_scunet_only.png'), model)
        np.testing.assert_array_equal(calls[0], source)
        assert len(calls) == 1
        report = json.loads((directory/'scunet_settings_and_timings.json').read_text())
        assert report['current_line_strength'] == 175
        assert report['scunet_only']['model_strength_percent'] == 100
        assert app.result is retained
        assert app.method.get() == 'Region cleanup only'
        assert 'Open 02_scunet_only.png' in app.status.get()
        assert (directory/'share_scunet_test.zip').is_file()
    finally:
        close_app(root)


def test_setup_reuses_working_torch_and_verifies_loader_in_fresh_process(monkeypatch):
    from stable_shift import scunet
    from stable_shift.app import subprocess, messagebox
    root, app = make_app()
    try:
        monkeypatch.setattr(messagebox, 'showerror', lambda *a: pytest.fail(str(a)))
        calls, weights = [], []
        def run(command, **kwargs):
            calls.append(command)
            return SimpleNamespace(returncode=0, stdout='', stderr='')
        monkeypatch.setattr(subprocess, 'run', run)
        monkeypatch.setattr(scunet, 'ensure_weights', lambda **k: weights.append(True))
        app.install_scunet('cpu')
        finish(root, app)
        pip = [c for c in calls if '-m' in c]
        assert len(pip) == 1 and pip[0][-1] == 'spandrel==0.4.2'
        assert calls[-1][-1].endswith('import spandrel')
        assert weights == [True]
        assert 'weights verified. Restart' in app.status.get()
    finally:
        close_app(root)


def test_failed_setup_retains_result_and_does_not_download_or_run_model(monkeypatch):
    from stable_shift import scunet
    from stable_shift.app import subprocess, messagebox
    root, app = make_app()
    try:
        errors = []
        monkeypatch.setattr(messagebox, 'showerror', lambda *a: errors.append(a))
        monkeypatch.setattr(subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=1, stderr='install failed', stdout=''))
        monkeypatch.setattr(scunet, 'ensure_weights', lambda **k: pytest.fail('Failed install must not download'))
        old = Image.new('RGB', (5, 7), 'blue')
        app.result = old
        method = app.method.get()
        app.install_scunet('nvidia')
        finish(root, app)
        assert errors and 'install failed' in str(errors[0])
        assert app.result is old and app.method.get() == method
    finally:
        close_app(root)


def test_scunet_actions_respect_busy_state(monkeypatch):
    from stable_shift.app import filedialog
    root, app = make_app()
    try:
        app.busy = True
        monkeypatch.setattr(filedialog, 'askdirectory', lambda **k: pytest.fail('Busy app must not start export'))
        app.compare_scunet()
        app.install_scunet('cpu')
        assert app.busy
    finally:
        close_app(root)
