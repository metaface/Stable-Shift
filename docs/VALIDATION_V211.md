# V2.11 shading contrast validation

## Diagnosis and change

The regression was reported in Compare colors, so both outputs used identical cleaned pixels with stroke cleanup and AA off. Native stage crops show some shading softened earlier by denoising/cleanup. Classic's correction, fitted to the local-cleanup baseline, adds back more tonal definition than the native RGB transform. The new color fit therefore makes the remaining shade look softer even though the RGB transform does not spatially blur pixels.

V2.11 retains the exact global RGB fit and adds source-derived tonal contrast restoration. It compares Classic and RGB renderings of the same cleaned image, extracts differences at 1.5-to-64-pixel scales, and restores supported contrast in CIELAB L. Positive local tonal covariance and source gradient coherence select contrast deficits; a small signal floor avoids quiet-region quantization noise. Contrast recovery has gain 1.5 and a four-L-unit bound, preserving broad RGB lighting and the fitted a/b colors before gamut conversion. No reference pixels enter this operation.

Classic is unchanged. A failed global fit still returns exact Classic. Identity/equal-rendering and flat-field cases have exact bypasses. Denoisers, source tracing, automatic strength, local/broad cleanup, stroke cleanup, AA and Preserve Edits are retained.

## Actual supplied inputs

Previously executed CPU BM3D candidates were replayed with exact source-pixel and selected-backend-argument checks. The cabin, beach and accepted color-off alley outputs remained byte-identical before color correction. Classic output matches the previous implementation exactly. The raw previous global output also matches V2.9/V2.10 exactly on the supplied cabin and beach pairs. The corrected result is a separate rendering from that same fit and input.

In one fixed tree-root measurement, mean lightness in a lit patch minus an adjacent shaded patch was:

| Rendering | Lightness contrast |
| --- | ---: |
| Classic | 5.23 L |
| Previous global RGB | 4.12 L |
| Restored shading | 4.92 L |

The patches are native coordinates: rows 1035–1069, columns 80–109 versus 25–49. The result recovers about 72% of the measured contrast deficit and reaches about 94% of Classic's contrast there. These are measurements of this local feature, not restoration accuracy or noise-removal percentages. Full images and native crops of roots, denim and face were inspected. The blue denim and neutral fur colors remain from the new RGB fit.

On the supplied beach pair, about 0.22% of RGB pixels change relative to the previous global result. Its 99th-percentile a/b difference is zero across in-gamut pixels. For the cabin, the corresponding 99th-percentile absolute a/b component change is about 0.59 LAB units after 8-bit RGB conversion. The operation changes L only before conversion; final RGB clipping/quantization prevents a guarantee of identical a/b values.

The actual warm alley reference is available only inline in the conversation, so no new real-alley color-fit claim is made. Its accepted color-off replay remains exact. Native Windows and GPU execution are unavailable; backend adapters are unchanged.

## Regression checks

Synthetic shading tests cover narrow and gradual transitions while retaining the new chroma and stable far-field lighting. Fine directionless grain must not be amplified, allowing one-level RGB quantization differences. Exact identity/equal/flat bypasses, dimension validation and repeated small color-drift cycles are checked. Existing tests retain colored-stroke, stitch-gap, smoke, AA, signed-stage and native desktop coverage.

Color-comparison tests count one backend run and check normal Run output against the matching exported method. The raw previous file is checked against the recorded fit coefficients. All outputs have strokes and AA off. The same fitted RGB transform is shared by the previous and restored-shading views. Packaging still runs from an isolated extraction without developer modules or new dependencies.
