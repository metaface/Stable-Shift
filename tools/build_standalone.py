"""Package only the current restoration runtime and its user guide."""
import argparse
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED
ROOT = Path(__file__).resolve().parent.parent


def build_standalone(output, root=ROOT):
    root, output = Path(root), Path(output)
    files = [root/name for name in ('README.md','requirements.txt','app.py','START_Stable_Shift.bat','docs/STANDALONE.md','docs/VALIDATION.md')]
    files += sorted((root/'stable_shift').glob('*.py'))
    output.parent.mkdir(parents=True,exist_ok=True)
    with ZipFile(output,'w',compression=ZIP_DEFLATED,compresslevel=9) as z:
        for path in sorted(files):
            entry=ZipInfo('StableShift/'+path.relative_to(root).as_posix(),date_time=(1980,1,1,0,0,0))
            entry.compress_type=ZIP_DEFLATED
            entry.external_attr=0o100644<<16
            z.writestr(entry,path.read_bytes(),compresslevel=9)
    return output


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=ROOT/'dist/Stable-Shift-v2.25.zip')
    print(build_standalone(parser.parse_args().out))
