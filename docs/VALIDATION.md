# V2.25 focused color validation

The uploaded test exposed another false fallback after V2.24's exposure fix.
Its fitted matrix passed the exposure-normalized stability tests. Robust's
held-out median Delta E was 6.293 versus Classic's 6.834, while their 80th
percentiles were 13.204 and 12.996. An older rule nevertheless rejected Robust
because 6.293 was greater than half of a flat-color prediction's 11.238 error.

V2.25 changes selection only. It compares a weighted held-out median/tail score
with Classic and the flat-color predictor. Comparable fits favor the selected
uniform RGB model, using a small quantization/tie allowance. A separate check
rejects substantial tail-error increases. Positive exposure, channel mixing,
conditioning and non-flat prediction remain validated. No fixed 8/16 error
ceiling or requirement to halve a flat guess's error is used.

Six scoped tests passed: supported fits with reference-only noise/detail,
rejection of constant-color collapse and unrelated pairings, and continued
acceptance of legitimate 0.1× and 6× exposure changes. Unchanged UI, denoiser
and cleanup tests were not repeated.

The uploaded 2048×2048 inputs and raw SCUNet result were replayed exactly. The
old Classic result first matched its saved PNG pixel-for-pixel. With V2.25,
the existing fitted RGB coefficients are accepted without changing them. The
new result is exactly that previously rejected Robust candidate applied after
the same deblotching. Automatic denoise, deblotch and color amounts remain
100/100/100. The user's model output is reused; no inference rerun is needed.

Cached cabin and beach controls keep their accepted color pixels exactly.
The SCUNet, deblotching, automatic-strength analysis and preview/blending files
remain byte-identical to V2.24. Only color selection and release metadata/docs
change. No statistical palette transfer, halo painting or new controls are
introduced. The retained runtime remains small and independent of retired
processing modules. Windows/CUDA execution was unavailable locally.

Held-out pixel agreement is not a semantic or universal perceptual score.
Large composition changes or genuinely unstable/inferior mappings can still
require the explicitly reported Classic fallback. Manual Classic remains
selectable; this change does not force all images to use a rejected RGB fit.
