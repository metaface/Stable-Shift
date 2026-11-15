# V2.13 reconstruction comparison

## Scope

V2.13 revisits the original quarter -> half -> full reconstruction design using the current selected denoiser, current automatic control and accepted native source tracing. It is an isolated comparison, not a byte-identical replay of the historical NLM/wavelet implementation or a replacement default. The accepted engine, color estimator, denoiser adapters, source tracing, local/broad cleanup, stroke cleanup and AA modules remain unchanged from V2.12.

Normal Run is unchanged. The comparison runs accepted full-resolution processing once, disables reference correction and finishing during that cleanup, and recovers the local baseline before broad correction. Independently reduced quarter/half edited inputs receive their own denoiser/local-cleanup processing with broad correction and native source copy-back disabled at those coarse scales. Their actual Auto settings are recorded separately. The native source-line map is shared at final output resolution.

## Candidates

- Accepted V2.12 cleanup is the control.
- Pyramid reconstruction uses quarter colors, a half-layer join, boundary-guided enlargement and a scale-supported denoised fine difference. Guided estimates stay within their local coarse-field envelopes. Exact source ink is restored separately.
- Solid colors assigns a robust coarse color to each detected edge-bounded paint region. Boundaries require sharpness and directional support across scales, rather than merely a different palette-bin number. This deliberately tests flat paint; missed edges can merge shading areas.
- Solid colors with gradients adds only fitted smooth LAB planes. Independent half/quarter support, held-out spatial tile errors, bounded amplitude and the retained bright-neutral texture cue control eligibility. A plane is not a native texture residual and does not identify an intentional material effect.

All views use one shared global RGB fit from the local baseline. A rejected fit disables reference correction in all comparison views; applying Classic's spatial field to a genuinely solid fill would invalidate this test. Normal Run's Classic/Robust choices and fallback remain unchanged.

## Important rejected approach

An initial solid-color prototype quantized a coarse palette into regions. On the actual beach input it turned the gradual blue-gray sparkle halos into large solid patches. That prototype was removed. The shipped experiment partitions by edge evidence instead, and its synthetic test explicitly includes a gradual halo that survives in both coarse layers. This does not establish that all real halos can be distinguished from intended paint.

## Full-size validation

The supplied 2048 x 2048 cabin, beach and alley edited inputs were tested. Existing actual full-resolution CPU BM3D candidates were reused only after verifying original pixels and exact selected backend arguments. Quarter and half CPU BM3D executions were computed independently from the edited sources. Their final-layer replays verify source reductions and every processing option before reusing those independently processed layers. No production cache/replay interface is added.

The cabin and beach use their actual color references and select the accepted Robust global transform. The alley test has reference correction off because its actual warm reference is unavailable as an original file. No new alley color-transfer claim is made.

The control rendering matches the accepted saved output pixel-for-pixel in all three cases. Every candidate retains all shared source-core pixels exactly before color and after the shared transform. These checks establish core equality, not preservation of every visible line's surrounding contrast.

Native crops include tree roots, denim, tail markings, beach sparkles and smoke. The pyramid improves the measured root-flank lightness separation relative to the accepted broad-cleanup result. Solid fills clear broad sparkle-halo variation but can flatten the weak tree shading boundary and simplify the tail's fades. The gradient exception does not solve every such case. Some boundary rims remain visible around smoke/colored marks. These tradeoffs are why none of the candidates is enabled in normal Run.

The established root-flank sample gives the following signed LAB lightness differences. This is one local diagnostic, not an image-wide quality score. The near-zero/reversed solid-mode values expose missed shading segmentation rather than a successful recovery:

| View | Root-flank lightness difference |
| --- | ---: |
| Accepted V2.12 | 4.117 |
| Pyramid | 5.231 |
| Solid colors | 0.068 |
| Solid with gradients | -0.498 |

## Automated and desktop checks

Tests cover color-gradient recovery from independent clean coarse layers while native noise is present; rejection of unrelated noise as a gradient; a bright-texture veto; constant RGB within each solid region; weak uninked shade separation; colored ink/stitch cores and their gaps; odd/tiny/all-protected images; and bounded coarse-color enlargement. Halo tests cover both native-only contamination and gradual contamination surviving at coarse scales.

The comparison is checked with manual and automatic settings. Tests verify independent source sizes, finishing off at all scales, exact protected pixels before/after one shared color transform, valid full-size exports, a required-input/output share archive, and field-free behavior when a reference fit is rejected. Native Tk exercises the new worker/export path and retains the user's previous normal Run result.

The complete accepted regression suite and isolated deterministic standalone package checks are retained. Linux CPU/Tk checks are available; native Windows and GPU execution are not available here. Their adapters/installers are unchanged. No new dependencies are required.

Final checks: **130 passed, 1 skipped** because the historical real-image fixture is unavailable. All eighteen retained processing/runtime modules outside the UI/package-version files are byte-identical to V2.12. The standalone archive builds with thirty-five runtime/documentation files; tests, user images and experimental validation artifacts are excluded.
