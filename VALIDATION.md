# V2.6 validation

## Scope

V2.6 adds a source-only strength controller around the existing backend and surface candidates. The source tracer defaults to the accepted V2.4 behavior again (`faint_continuity=False`). V2.5 continuation remains available to API/legacy tests. Palette estimation, local cleanup, broad normalization and Preserve Edits algorithms are retained.

`region_cleanup.py`, `surface_normalization.py`, `frozen_palette.py`, `difference_guard_core.py`, `difference_guard_multimap.py`, `image_inputs.py` and requirements are byte-identical to V2.4. CPU/GPU BM3D, NLM, boundary diffusion, palette and Preserve Edits function ASTs match V2.4. Auto supplies different strengths or skips a fine stage; it does not change a backend implementation.

## Smoke diagnosis

A native 440×760 crop from the supplied 2048×2048 alley source was processed through separate CPU stages: raw BM3D at manual strengths 100/100, legacy guards, source copy-back, local cleanup and broad normalization, with palette correction off. The raised/outlined smoke appearance is already visible in raw maximum BM3D. Keeping a sharp boundary while flattening interior/background cues further makes the smoke read as a cutout. Source protection is therefore not the sole cause.

This identifies an early processing stage in a controlled reproduction. It does not establish which historical release first showed the artifact, or reproduce the exact GPU/color-corrected screenshot.

## Actual full-resolution inputs

Both supplied edited sources were tested at 2048×2048. Strength ceilings were 100, similarity range 40, local radius 16, hard guard 100, soft guard 60 and shading sensitivity 35. Original color-reference files were absent from these compact line-test ZIPs, so these structure/strength checks used palette correction off. New comparison exports include the reference when it fits the share budget.

| Measurement | Alley/smoke | Denim/cabin |
| --- | ---: | ---: |
| Estimated fine LAB sigma, L | 0.172 | 0.190 |
| Estimated fine LAB sigma, a / b | 0.290 / 0.270 | 0.293 / 0.255 |
| Selected fine L / C slider | 0 / 0, skipped | 0 / 0, skipped |
| Mean luminance surface permission | 8.44% | 26.37% |
| Mean chroma surface permission | 21.75% | 45.66% |
| Auto total processing time | 15.45 s | 16.33 s |
| Original source-core pixels changed before palette | 0 | 0 |

The nearly equal fine-scatter estimates alone cannot distinguish these cases. Medium colored variation and directional structure produce different surface permissions. These averages are weights, not percentages of noise removed.

The alley received a full manual-versus-auto export using actual CPU BM3D for the maximum manual result. Manual total was 328.64 seconds, including 314.01 seconds of BM3D; automatic skipped BM3D. This compares different processing, not faster equivalent denoising. Both variants had identical source masks (719,918 protected pixels); changed common core pixels were zero. The controlled share ZIP was 28,613,814 bytes and recorded its omitted optional images.

Native crops from full-image outputs were inspected. Auto retained pavement seams and interior texture in the smoke, without the pronounced maximum-strength rim. Denim showed moderate mottling reduction, with substantial residual texture compared with maximum manual cleanup. The full denim stage residuals summed exactly to total change. Neither image establishes general semantic noise detection.

## Automated and regression checks

The suite completed with **73 passed, 1 skipped** under an actual Linux Tk display. It includes actual CPU BM3D and native Tk/drag-drop integration.

New checks cover:

- Fine-noise response, requested ceilings, invalid input and exact backend arguments.
- Different cleanup permission for colored mottling versus gray structure; zero permission on source cores and reduced permission nearby.
- Exact zero-weight bypass, bounded weights, chroma-only limiting and protected RGB retention.
- An uncorrupted shaded image remaining byte-identical over three automatic passes, with fine denoising skipped.
- Reduced error against known clean synthetic colored surfaces; the conservative correlated-mottle test improves MSE by about 7%, rather than claiming complete removal.
- Actual small CPU BM3D reducing known independent random-noise MSE by more than half.
- Reference independence of detection, output geometry and processing when palette correction is off.
- Raw denoiser plus guard signed residuals equaling the combined handoff; local plus broad residuals equaling cleanup; all processing stages summing to total.
- Rejecting a manual cached backend candidate when automatic settings require a different run.
- Manual/auto comparison using separately selected backend settings, one frozen palette field, exact common protection, full-size input/output export and a compact share archive.
- The actual Compare auto button completing its worker and exporting both variants. Existing image drop slots, themes, busy guards, saving actual run settings and stale-result clearing remain covered.

A native 128×128 CPU regression with fine/local/broad strengths 100, similarity range 40 and Auto off matched V2.4 **byte-for-byte in output RGB and source mask**. Existing cleanup and optional faint-line tests also pass.

## Limits

No GPU or Windows Explorer end-to-end execution is available in this Linux environment. GPU adapters are retained, not newly benchmarked. Palette bias, color-induced contrast compression, edit-replacement issues and sparkle halos are not addressed here. Gray-only broad contamination and uncertain texture can remain; intentional colored texture can be softened. The controller is calibrated conservatively for these illustrative inputs and BM3D strength scales, not validated across every generation model or image style.
