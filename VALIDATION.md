# V2.5 validation

## Scope and retained controls

This test changes source tracing to retain faint segments between compatible existing anchors. V2.4's `region_cleanup.py`, `surface_normalization.py`, `frozen_palette.py`, palette/core modules, input loader and requirements are byte-identical. CPU/GPU BM3D implementations and parameters are unchanged; backend dispatch is factored out so a controlled comparison can reuse one unguarded result.

The comparison switches `faint_continuity` only. Both variants get the same backend candidate, local/broad cleanup settings and frozen palette field fitted from the V2.4 baseline's pre-broad local result. Source barriers can change the cleanup result, which is the intended consequence of protecting a previously missed segment.

## Supplied 70/100 archives

Both smaller archives were read successfully at native 2048×2048 resolution. They use GPU BM3D, denoise 100/100, local cleanup 100, LAB range 40, brightness cleanup 100, radius 16, hard/soft guards 100/60 and shading sensitivity 35. Broad maximum is the only configured difference: 70 versus 100.

Both masks contain 551,687 protected pixels (13.153% of the image), with identical original trace/core geometry. In each run the extra broad pass changes **zero** protected pixels, and its maximum channel change within three pixels of the core is **one RGB level**. The recorded mean near-core changes are 0.000974 at 70 and 0.002900 at 100. Broad mean RGB changes are 0.371842 and 0.559987 respectively.

Native crops of cabin lines above the window, the face, the exposed-torso/overalls edge, denim seams and trees were inspected. Some weak-segment coverage is interrupted in the earlier mask/shared baseline. Palette conversion also compresses some faint local contrasts; protected adjacent-pixel statistics are not counts of lost strokes. The new test targets missed source segments and leaves that palette behavior fixed.

The archives contain processed baseline pixels and the original trace/core, **not the original edited RGB input**. Candidate-geometry exploration used the supplied original anchors with a processed-image guide, explicitly as a proxy. That probe suggested additional protection over about 0.291% of the image, but it is not an end-to-end restoration or a measured recovery of the user's original strokes. No new result image for that exact original/GPU run is claimed. The new compact export includes `edited_source.png` so future tracing tests can use the actual source.

## Automated checks

Full suite under the test display: **59 passed, 1 skipped**. The skipped test requires an old historical local fixture. After final cache-validation and version-label changes, the affected line/GUI tests were rerun: **11 passed**.

```text
DISPLAY=:100 OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 python -m pytest -q
```

New checks cover:

- A synthetic low-contrast stroke whose middle fails the old confidence threshold gains full source-core coverage across that middle. Previously protected pixels are retained.
- A blank source gap is not drawn into a stroke, and one-ended faint tails do not grow.
- Opposite gradient polarities cannot supply a bridge; slanted strokes work beyond a 45-degree grid.
- Pure noisy flat input gains less than 1% additional protection in the controlled noise test.
- A shared-denoiser comparison recovers the known weak stroke at the source RGB while the old variant visibly loses contrast. The backend runs once, and its cached array is not mutated.
- The comparison changes zero previous core pixels before/after the shared palette; new core pixels retain exact source RGB before color correction.
- Saved signed denoise, cleanup and palette residuals sum exactly to total change.
- Compact ZIP contents include full outputs, masks, settings and edited source, and exclude large NPZ files.
- The actual native Tk **Compare lines** button completes its worker, exports both variants and creates the share ZIP.

Retained tests cover CPU BM3D behavior, explicit GPU failures, source protection, V2.4 shading/blotch regressions, palette equivalence, input/reference independence, native file-drop callbacks, themes, image sizes and saved settings.

A separate native 128×128 CPU BM3D exercise compared the accepted V2.4 implementation with V2.5 at `faint_continuity=False`, using noise/local/broad strength 100 and LAB range 40. **Result RGB and source masks matched byte-for-byte.**

## Full-resolution original-image comparison

Used the supplied beach reference and edited hat/ribbon input at their original 2048×2048 size. No generative re-render or additional character reference was used as ground truth. This is an actual original-input CPU comparison, unlike the processed-guide pants probe above. Artwork is not committed to the repository.

Settings match the stress test: CPU BM3D 100/100, local cleanup 100, brightness cleanup 100, LAB range 40, radius 16, broad maximum 100, source tracing on and guards 100/60.

- Backend ran **once**, taking 323.02 s on this development CPU.
- Old/new source analysis took **1.03 / 2.09 s**.
- Old/new local-plus-broad cleanup took **12.57 / 12.21 s**.
- Whole comparison processing before export took **353.87 s**.
- Protected pixels increased **875,602 → 893,108**, adding **17,506 pixels / 0.417% of the image**.
- Previous core pixels removed: **0**.
- Previous core RGB changed: **0 before palette and 0 after the shared field**.
- New core pixels differing from original source before palette: **0**.
- Mean source-RGB error on the added pixels was **4.700/255 in the old result and 0 in the new result**. Exact source copying guarantees the latter; it is not a percentage of artistic detail restored or noise removed.
- Mean absolute final RGB difference between variants was **0.184/255**. Changes extend outside the added core because the existing cleanup uses the updated barriers; cleanup settings and algorithms are fixed.
- Signed stage accounting was checked on both full exported NPZ files and matched exactly.
- The generated compact ZIP is **24.33 MiB**, below the download tool's 32-MiB limit.

Native crops of hat weave, flower/ribbon outlines, fur and crystal facets were inspected. Changes are targeted and modest; residual noise and sparkle halos remain. Keeping the source exactly also keeps any noise embedded in that source stroke.

GPU execution and Windows Explorer end-to-end behavior remain unverified in this Linux executor. Unsupported long gaps, absent source strokes and contrast compressed by palette conversion can still remain faint. This is a test of source retention, not semantic line reconstruction, stroke enhancement or antialiasing.
