# V2.9 color and optional antialiasing validation

## Scope

Accepted V2.8 automatic strength, source tracing, local/broad cleanup and CPU/GPU denoiser adapters are retained. The four analysis/tracing/cleanup modules are byte-identical to the accepted layout. New finishing is opt-in: Classic color correction remains default and AA starts off. Preserve Edits is unchanged. No Forge hooks or lighting progression controls are added.

Robust global fits a single 3×3 RGB matrix and two pivots from eligible coarse paired colors. Eight robust reweighting steps and a small identity prior reduce outlier influence. Independent held-out tiles must improve agreement over the exact Classic baseline; insufficient variation, collapsing/extreme coefficients and poorly explained colors trigger Classic fallback. The new transform applies native colors uniformly, without a spatial reference field. Tests include changed reference objects, grid contamination, degenerate/unrelated references, identity, and repeated small color drift. These are bounded regression heuristics, not semantic correspondence or noise recognition.

## Actual full-size inputs

Previously executed CPU BM3D candidates were replayed on the supplied 2048×2048 cabin, beach and alley sources. Source pixels and exact estimated backend arguments were checked before each candidate was reused through a validation-only monkeypatch. No production automatic cache interface was added. All three accepted outputs remained byte-identical with the original finishing settings: zero changed RGB pixels. The alley replay has color correction off; the actual warm reference exists only inline in the conversation and was not available as an original file for a new color test.

For the supplied cabin and beach reference pairs, the new estimator selected Robust global. With cleanup fixed, held-out low-gradient sample errors were:

| Pair | Classic median ΔE76 | Robust global median ΔE76 | Classic 80th percentile | Robust global 80th percentile |
| --- | ---: | ---: | ---: | ---: |
| Extreme cabin | 5.09 | 3.50 | 12.25 | 7.57 |
| Beach | 3.44 | 2.38 | 5.68 | 4.51 |

These are coarse paired-color fit measurements, not image-wide restoration accuracy, noise removal percentages, or proof of correct object correspondence. Native crops and full previews were inspected: cabin denim moves toward blue and the bright fur loses much of its yellow cast. Some mismatch remains, including colors already clipped or collapsed in the edited image. No new full-size GPU execution was performed; the GPU adapter is unchanged.

## AA and desktop checks

Synthetic diagonal edges were compared with 16× supersampled coverage; the directional filter at strength 35 reduced stair-step error while retaining flat pixels exactly. Straight vertical strokes and short stitch centers retain contrast. AA at zero is an exact bypass. Full-size cabin crops were inspected with AA off and 35: the effect is light edge smoothing, not reconstructed clean linework. One local CPU timing for the 2048×2048 post-color AA pass at 35 was approximately 0.43 seconds; hardware and run-to-run timing differ.

Tests verify that repeated AA previews do not accumulate, disabling AA restores exact post-color pixels, signed stage maps telescope, and upstream actual-run settings survive later control changes. Native Tk tests cover worker completion, color-comparison export, quick AA preview without another denoiser call, save reports, input replacement, drag/drop and themes. Color comparisons are checked with manual and automatic cleanup: one backend run, identical cleanup for both color methods, AA off, and outputs matching their corresponding normal Run settings. Compare auto forces its shared Classic field and AA off even when the finishing controls request otherwise.

The full suite is run with a Linux display, NumPy/OpenCV, CPU BM3D and tkinterdnd2. The historical real-image fixture test is skipped because its old absolute-path fixture is absent. Native Windows and GPU execution remain untested here. The isolated standalone archive test exercises actual package startup without developer modules; no new dependencies are required.
