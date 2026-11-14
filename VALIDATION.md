# V2.7 validation

## Problem reproduced

The supplied V2.6 share export used GPU BM3D with all strength ceilings 100, similarity range 40 and radius 16. Its automatic controller measured native LAB scatter of approximately 0.190 / 0.293 / 0.255, selected denoiser strengths 0/0 and skipped BM3D. Actual local and broad mean changes were only 0.389 and 0.357 RGB levels. The grid was present before palette correction; the manual output suppressed it much more strongly.

Native scatter alone is an inadequate cue for this correlated contamination. V2.6 also limited surface corrections too strongly and did not limit a stronger backend by location. V2.7 adds coarser eligible-interior measurements and spatial limits at the backend handoff.

## Processing retained

`region_cleanup.py`, `surface_normalization.py`, `frozen_palette.py`, `difference_guard_core.py`, `difference_guard_multimap.py`, `image_inputs.py`, `line_protection.py` and requirements are byte-identical to V2.6. CPU/GPU BM3D implementations, palette estimation and edit replacement are unchanged. The source tracer remains the V2.4 baseline by default; faint continuation stays optional.

Auto derives stronger candidate settings from native and coarser source analysis. Coarse samples require at least 64 eligible interior samples per channel, with protected edges excluded. Scale compensation is a white-noise-equivalent cue, not a claim that the measured variation is certainly noise. Restoration pixels remain at the original resolution.

The guarded backend correction is then limited independently in LAB luminance/chroma. Local and broad candidates retain their own limits. Joint luminance/chroma coherence and a six-pixel source-protection fade replace the overly restrictive earlier permissions; independent native grain can authorize a fine gray correction without broad brightness flattening.

## Full-resolution checks

Both supplied sources were processed at 2048×2048 through the actual CPU BM3D adapter, without reusing a differently configured backend candidate. Ceilings were 100, LAB range 40, radius 16, hard guard 100, soft guard 60 and shading sensitivity 35.

| Automatic choice | Denim/cabin | Alley/smoke |
| --- | ---: | ---: |
| Native L scatter | 0.190 | 0.172 |
| Maximum eligible coarse equivalent L scatter | 5.592 | 6.169 |
| Selected denoiser L slider | 79.08 | 87.92 |
| Selected denoiser C slider | 26.66 | 16.71 |
| Backend executed | Yes | Yes |
| Mean surface/backend L permission | 59.00% | 30.65% |
| Mean surface/backend C permission | 68.98% | 44.00% |
| Protected source-core pixels changed before palette | 0 | 0 |

Candidate settings are not uniform applied strengths: the alley can need a strong candidate for some colored interiors while smoke receives much less luminance correction. Permissions are weights, not percentages of noise removed.

The newly supplied denim color reference was used in its normal final output. The alley reference was absent from its earlier compact ZIP, so the smoke structure check kept palette correction off. A separate denim preview approximated the old fixed palette from its quantized manual before/after pair solely to inspect cleanup at comparable colors. That approximation is not part of the application. The actual Compare auto workflow still freezes one exact manual-baseline field for both variants.

Native crops were inspected for denim, cabin/window lines, tree shading, smoke, clothing seams and the parking area. V2.7 showed visibly greater denim blotch reduction than V2.6, with some residual texture. Smoke kept interior pavement cues without the pronounced maximum-strength cutout rim. Core pixels alone do not establish perfect contrast or retention of every untraced detail.

Both full-image stage checks passed: raw backend + legacy guards + automatic backend limiting equals the controlled handoff; local + broad equals combined cleanup; denoising + cleanup + palette equals total RGB change. No protected source-core pixel changed before color correction.

Both CPU jobs ran concurrently and took approximately 659 seconds each including contention, with about 15 seconds of surface cleanup per image. These are not isolated performance benchmarks and do not predict GPU timing. Unlike V2.6 on these inputs, the new automatic mode actually executes the denoiser.

## Measured denim texture

A fixed flat patch at x=1260–1399, y=1230–1389 was selected before measuring the new output. All measurements below use native pre-palette LAB luminance, so reference colors cannot account for the reduction.

| Measurement | Original | V2.6 Auto | V2.7 Auto CPU | Supplied manual maximum GPU |
| --- | ---: | ---: | ---: | ---: |
| L high-pass RMS, Gaussian sigma 1 | 0.447 | 0.318 | 0.217 | 0.190 |
| L high-pass RMS, sigma 4 | 0.989 | 0.719 | 0.532 | 0.482 |
| L high-pass RMS, sigma 8 | 1.215 | 0.935 | 0.743 | 0.690 |
| Grid-band power / V2.6 Auto power | 3.878 | 1.000 | 0.092 | 0.002 |

Grid power uses a Hann-windowed, plane-detrended FFT, summing the axial 0.10–0.15 cycles/pixel bands with transverse frequency below 0.012. V2.7 reduced this measured grid-band power by about 90.8% relative to V2.6, and sigma-4/sigma-8 RMS by about 26.0%/20.5%. This describes one selected flat patch and frequency band, not total image noise or a general restoration score. The manual GPU image is context, not a CPU/GPU equivalence test; it remains smoother in this patch but produces the unwanted smoke behavior when applied globally.

## Automated and baseline checks

**76 tests passed, 1 skipped** under an actual Linux Tk display. The skip is a historical image fixture that is unavailable in this environment. Tests include actual CPU BM3D, native drag/drop and the real Compare auto button.

New regressions ensure that correlated colored contamination can activate the backend despite native scatter below the old skip thresholds. A known corrupted color patch improves MSE by more than 40% against its clean original while neighboring legitimate gray detail stays byte-identical. A deliberately destructive mocked backend confirms that spatial limiting restores those quiet gray pixels, rather than relying on a gentle backend to hide the problem.

Existing checks still cover strength ceilings, exact backend arguments, source/reference independence, three unchanged passes of a clean shaded image, fine random-noise reduction, source-core retention, actual residual accounting, one shared comparison palette, compact ZIP contents and saving actual run settings. The new comparison exports the actual raw automatic backend and its controlled handoff when the share budget permits.

A separate native 128×128 CPU regression with Auto off matched the accepted V2.4 output RGB and source mask byte-for-byte. The retained cleanup, faint-line and legacy comparison tests also passed.

## Limits

GPU execution and Windows Explorer end-to-end behavior remain unverified here. Their adapters/input paths are retained. No color-estimation, antialiasing, edit-replacement, neural restoration or lighting-control change is included. Gray-only broad contamination can remain, and intentional colored texture can be softened. Coarse variation and spatial permissions remain heuristics rather than semantic recognition of artistic intent.
