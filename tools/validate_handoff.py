"""Optional reproducible real-image exercise; user supplies the handoff ZIP."""
import argparse
from io import BytesIO
import json
from pathlib import Path
import zipfile

from PIL import Image

from stable_shift.engine import Options
from tools.blotch_comparison import export_blotch_comparison


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--handoff', required=True, help='Path to light_ai_restoration_handoff.zip')
    parser.add_argument('--out', required=True, help='Comparison output directory')
    parser.add_argument('--backend', default='CPU BM3D', choices=['CPU BM3D', 'GPU BM3D', 'NLM', 'Region cleanup only'])
    args = parser.parse_args()
    with zipfile.ZipFile(args.handoff) as archive:
        prefix = 'light_ai_restoration_handoff/inputs/'
        def read(name):
            with Image.open(BytesIO(archive.read(prefix+name))) as im:
                return im.convert('RGB')
        clean = read('clean_seated_reference.png')
        edited = read('degraded_hat_and_ribbon_target.png')
    options = Options(method=args.backend, noise=55, color_noise=55, cleanup=60,
                      cleanup_luma=60, cleanup_range=12, hard_guard=100,
                      soft_guard=60, blotch_strength=70, color_match=True)
    summary = export_blotch_comparison(clean, edited, options, args.out, lambda x: print(x, flush=True))
    checks = summary['line_preservation_check']
    if checks['changed_before_palette'] or checks['changed_after_palette']:
        raise RuntimeError('Protected-pixel preservation check failed; inspect exported diagnostics.')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
