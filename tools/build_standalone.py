"""Build the small standalone ZIP without tests or historical experiments."""
import argparse
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED


ROOT = Path(__file__).resolve().parent.parent
ROOT_FILES = ('README.md', 'requirements.txt', 'app.py',
              'START_Stable_Shift.bat', 'CLEANUP_OLD_FILES.bat')
MAINTENANCE_FILES = ('tools/__init__.py', 'tools/tidy_legacy_files.py')
USER_DOCS = ('docs/STANDALONE.md', 'docs/CLEANUP.md', 'docs/VALIDATION_V29.md', 'docs/VALIDATION_V210.md', 'docs/VALIDATION_V212.md', 'docs/VALIDATION_V213.md')


def build_standalone(output, root=ROOT):
    root, output = Path(root).resolve(), Path(output)
    files = [root/name for name in ROOT_FILES+MAINTENANCE_FILES+USER_DOCS]
    files += sorted((root/'stable_shift').rglob('*.py'))
    if not (root/'stable_shift/__main__.py').is_file():
        raise ValueError('The active stable_shift package is missing.')
    missing = [str(path.relative_to(root)) for path in files if not path.is_file()]
    if missing:
        raise ValueError('Required package files are missing: '+', '.join(missing))
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, 'w', compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(files):
            relative = path.relative_to(root)
            if '__pycache__' in relative.parts:
                continue
            entry = ZipInfo('StableShift/'+relative.as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, path.read_bytes(), compresslevel=9)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT/'dist/Stable-Shift-v2.13.zip')
    args = parser.parse_args()
    print(build_standalone(args.out))


if __name__ == '__main__':
    main()
