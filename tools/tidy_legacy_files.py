"""Move known old root scripts into a backup after installing the new layout."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
LEGACY_FILES = (
    'START_Difference_Guard.bat', 'STANDALONE.md', 'VALIDATION.md',
    'auto_comparison.py', 'automatic_strength.py', 'blotch_comparison.py',
    'comparison.py', 'difference_guard_core.py', 'difference_guard_multimap.py',
    'engine.py', 'frozen_palette.py', 'image_inputs.py', 'line_comparison.py',
    'line_protection.py', 'region_cleanup.py', 'stage_maps.py',
    'surface_normalization.py', 'validate_blotch_pair.py', 'validate_handoff.py',
    'test_automatic.py', 'test_blotches.py', 'test_engine.py', 'test_faint_lines.py',
    'test_ui.py', 'test_v11.py', 'test_v2.py', 'test_v21.py',
    'START_Difference_Guard_Edge_Lab.bat', 'START_Difference_Guard_Boundary_Lab.bat',
    'difference_guard_gui.py', 'difference_guard_cli.py', 'compare_denoisers.py',
    'difference_guard_denoise.py', 'difference_guard_reconstruction.py',
    'difference_guard_bottom_up.py', 'VERSION_NOTES.md',
)


def tidy_legacy_files(root=ROOT, apply=False):
    root = Path(root).resolve()
    required = ('stable_shift/__main__.py', 'app.py', 'START_Stable_Shift.bat')
    if any(not (root/name).is_file() for name in required):
        raise ValueError('Install the new Stable Shift layout here before moving old files.')
    paths = [root/name for name in LEGACY_FILES
             if (root/name).is_file() and not (root/name).is_symlink()]
    planned = [{'name':path.name, 'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                'bytes':path.stat().st_size} for path in paths]
    result = {'applied': bool(apply), 'root': str(root), 'files': planned, 'backup': None}
    if not apply or not paths:
        return result
    backup_root = root/'_legacy_backup'
    if backup_root.is_symlink():
        raise ValueError('The backup directory must be inside this app folder.')
    backup = backup_root/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    backup.mkdir(parents=True, exist_ok=False)
    result['backup'] = str(backup)
    manifest = {**result, 'moved': [],
                'restore': 'Move the listed files from this backup to the app root to restore them; do not overwrite newer files.'}
    manifest_path = backup/'manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    for path in paths:
        path.rename(backup/path.name)
        manifest['moved'].append(path.name)
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT, help='Updated app folder')
    parser.add_argument('--apply', action='store_true', help='Move listed files; default only lists them')
    args = parser.parse_args()
    result = tidy_legacy_files(args.root, args.apply)
    for item in result['files']:
        print(item['name'])
    if result['backup']:
        print('Moved '+str(len(result['files']))+' old files into '+result['backup'])
    elif result['files']:
        print('Preview only. Add --apply to move these files into a backup.')
    else:
        print('No known old root files need moving.')


if __name__ == '__main__':
    main()
