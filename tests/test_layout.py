import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
from zipfile import ZipFile

import pytest

from tools.build_standalone import ROOT, build_standalone
from tools.tidy_legacy_files import tidy_legacy_files


def updated_folder(tmp_path):
    root = tmp_path/'Stable Shift café'
    (root/'stable_shift').mkdir(parents=True)
    for name in ('stable_shift/__main__.py', 'app.py', 'START_Stable_Shift.bat'):
        (root/name).write_text('new application', encoding='utf-8')
    return root


def test_legacy_tidy_previews_and_preserves_old_bytes_and_user_data(tmp_path):
    root = updated_folder(tmp_path)
    previous = b'# user-modified old engine\r\n'
    (root/'engine.py').write_bytes(previous)
    (root/'difference_guard_gui.py').write_text('old GUI')
    (root/'custom_script.py').write_text('my custom script')
    (root/'.venv').mkdir();(root/'.venv/marker').write_text('installed environment')
    (root/'input.png').write_bytes(b'original image')
    (root/'result.settings.json').write_text('{"keep":true}')
    preview = tidy_legacy_files(root)
    assert {f['name'] for f in preview['files']} == {'engine.py', 'difference_guard_gui.py'}
    assert (root/'engine.py').read_bytes() == previous
    assert not (root/'_legacy_backup').exists()
    result = tidy_legacy_files(root, apply=True)
    backup = Path(result['backup'])
    assert (backup/'engine.py').read_bytes() == previous
    manifest = json.loads((backup/'manifest.json').read_text())
    assert set(manifest['moved']) == {'engine.py', 'difference_guard_gui.py'}
    item = next(f for f in manifest['files'] if f['name'] == 'engine.py')
    assert item['sha256'] == hashlib.sha256(previous).hexdigest()
    assert not (root/'engine.py').exists()
    assert (root/'app.py').read_text() == 'new application'
    assert (root/'custom_script.py').read_text() == 'my custom script'
    assert (root/'.venv/marker').read_text() == 'installed environment'
    assert (root/'input.png').read_bytes() == b'original image'
    assert (root/'result.settings.json').read_text() == '{"keep":true}'
    assert tidy_legacy_files(root, apply=True)['backup'] is None
    assert len(list((root/'_legacy_backup').iterdir())) == 1


def test_legacy_tidy_requires_the_new_app_before_moving_anything(tmp_path):
    (tmp_path/'engine.py').write_text('working old application')
    with pytest.raises(ValueError, match='Install the new'):
        tidy_legacy_files(tmp_path, apply=True)
    assert (tmp_path/'engine.py').read_text() == 'working old application'


def test_module_and_compatible_script_entry_points_use_the_same_main(monkeypatch):
    from stable_shift import app
    calls = []
    monkeypatch.setattr(app, 'main', lambda: calls.append(True))
    runpy.run_module('stable_shift', run_name='__main__')
    runpy.run_path(str(ROOT/'app.py'), run_name='__main__')
    assert calls == [True, True]
    assert app.ROOT == ROOT


def test_packaged_startup_error_is_logged_in_the_app_folder(tmp_path, monkeypatch):
    from stable_shift import app
    calls = []
    class Root:
        def mainloop(self):
            calls.append('loop')
    monkeypatch.setattr(app, 'ROOT', tmp_path)
    monkeypatch.setattr(app.tk, 'Tk', Root)
    monkeypatch.setattr(app, 'TkinterDnD', None)
    monkeypatch.setattr(app, 'App', lambda root, available, error: calls.append((available, error)))
    app.main()
    assert calls[0][0] is False
    assert 'START_Stable_Shift.bat' in (tmp_path/'startup.log').read_text()


def test_standalone_zip_is_repeatable_and_runs_without_developer_files(tmp_path):
    first = build_standalone(tmp_path/'first.zip')
    second = build_standalone(tmp_path/'second.zip')
    assert first.read_bytes() == second.read_bytes()
    with ZipFile(first) as archive:
        names = archive.namelist()
        assert 'StableShift/START_Stable_Shift.bat' in names
        assert 'StableShift/stable_shift/engine.py' in names
        assert 'StableShift/tools/tidy_legacy_files.py' in names
        assert not any('/tests/' in name or '/__pycache__/' in name for name in names)
        assert not any(name.endswith(('line_comparison.py', 'blotch_comparison.py', 'build_standalone.py')) for name in names)
        archive.extractall(tmp_path/'isolated')
    folder = tmp_path/'isolated/StableShift'
    for name in ('engine.py', 'difference_guard_core.py', 'difference_guard_multimap.py'):
        (folder/name).write_text("raise RuntimeError('stale root module must not be imported')\n")
    env = dict(os.environ)
    env.pop('PYTHONPATH', None)
    script = '''
from pathlib import Path
import sys
from PIL import Image
from stable_shift.engine import Options, restore_quality, preserve_edits
from stable_shift.app import ROOT
assert ROOT == Path.cwd()
source = Image.new('RGB', (32, 32), (120, 140, 160))
out, maps = restore_quality(source, source, Options(method='Region cleanup only', auto_strength=True, color_match=False))
assert out.size == source.size
edited, _ = preserve_edits(source, source, Options())
assert edited.size == source.size
assert 'tools.line_comparison' not in sys.modules
assert 'tools.blotch_comparison' not in sys.modules
print('isolated package works')
'''
    proc = subprocess.run([sys.executable, '-c', script], cwd=folder, env=env,
                          capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stdout+proc.stderr
    assert 'isolated package works' in proc.stdout
