"""Replay a supplied pre-palette comparison without rerunning a denoiser.

The original edited input and palette field are not reconstructed from PNGs.
Metadata is read as numeric settings only; attached prose is never executed.
"""
from argparse import ArgumentParser
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from surface_normalization import normalize_surfaces


def replay(directory, out, source_mask=None, strength=None):
    directory, out = Path(directory), Path(out)
    with Image.open(directory/'00_v21_before_palette.png') as image:
        baseline = np.array(image.convert('RGB'))
    with Image.open(directory/'01_broad_before_palette.png') as image:
        previous = np.array(image.convert('RGB'))
    if baseline.shape != previous.shape:
        raise ValueError('The before-palette pair must have identical dimensions.')
    settings = json.loads((directory/'blotch_settings_and_timings.json').read_text(encoding='utf-8-sig'))['options']
    if source_mask is not None:
        with Image.open(source_mask) as image:
            core = np.asarray(image.convert('L')) > 127
        mask_note = 'Supplied original source-core PNG.'
    else:
        # Every actual core pixel is unchanged in the V2.3 pair. Freezing the
        # entire unchanged set is stricter, and also freezes some quiet pixels.
        # Never claim it recreates the original 13%-of-image tracer mask.
        core = np.all(baseline == previous, axis=2)
        mask_note = 'Conservative unchanged-pixel superset; original source mask unavailable.'
    maximum = settings['blotch_strength'] if strength is None else strength
    candidate, _, report = normalize_surfaces(baseline, maximum,
        settings['cleanup_range'], settings['cleanup_luma'], core, diagnostics=False)
    kernel = np.ones((49, 49), np.uint8)
    lower = cv2.erode(baseline, kernel, borderType=cv2.BORDER_REFLECT)
    upper = cv2.dilate(baseline, kernel, borderType=cv2.BORDER_REFLECT)
    def violations(image):
        return int(np.count_nonzero(np.any((image < lower) | (image > upper), axis=2)))
    lab_before = cv2.cvtColor(baseline.astype(np.float32)/255, cv2.COLOR_RGB2LAB)
    lab_after = cv2.cvtColor(candidate.astype(np.float32)/255, cv2.COLOR_RGB2LAB)
    l_step = lab_after[:, :, 0]-lab_before[:, :, 0]
    report.update({
        'version': '2.4', 'resolution': [baseline.shape[1], baseline.shape[0]],
        'mask_note': mask_note, 'frozen_pixels_percent': float(100*core.mean()),
        'frozen_pixels_changed': int(np.count_nonzero(np.any(candidate[core] != baseline[core], axis=1))),
        'previous_local_channel_envelope_violations': violations(previous),
        'candidate_local_channel_envelope_violations': violations(candidate),
        'candidate_L_step_min_max': [float(l_step.min()), float(l_step.max())],
        'scope': 'Pre-palette cleanup replay only. No original-source tracing, denoiser or palette rerun.',
    })
    out.mkdir(parents=True, exist_ok=True)
    Image.fromarray(candidate).save(out/'04_local_before_palette.png')
    (out/'local_replay_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path, help='Extracted comparison directory')
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--source-mask', type=Path, help='Optional shared_source_line_core.png from that run')
    parser.add_argument('--strength', type=float, help='Default: original comparison maximum')
    args = parser.parse_args()
    print(json.dumps(replay(args.input, args.out, args.source_mask, args.strength), indent=2))


if __name__ == '__main__':
    main()
