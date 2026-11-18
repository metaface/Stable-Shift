# Stable Shift

Standalone cleanup and color restoration for Stable Diffusion outputs. **V2.18** validates connected stroke paths before restoring or fitting source ink. Tiny fragments cannot seed a reconstructed line, fitting samples must belong to the same path, and compact filled details receive a separate exclusion. The V2.17 median cleanup has been removed. No new dependencies.

Double-click **START_Stable_Shift.bat**. Load or drop your reference and edited image, then use Run / Preview. Automatic strength starts enabled; source geometry always comes from the edited image. The reference supplies colors only.

## Updating an existing folder

For a Git checkout, close the app and pull the branch you are testing with Git Bash. Git handles tracked file removals; no cleanup script is needed. Keep using **START_Stable_Shift.bat**. The existing `.venv` is reused; this version adds no dependencies.

For a fresh ZIP installation, extract into a new folder and use the Start launcher. It installs base requirements; optional CPU/GPU BM3D can be installed with the app buttons. For older installations updated by copying a ZIP over existing files, see [cleanup notes](docs/CLEANUP.md). `python app.py` remains supported.

## Live traced-stroke test

Load the usual pair/settings and choose **Prepare live pyramid**. Then use **Line reconstruction %**:

- **0%**: traced source preservation, without stroke fitting.
- **100%**: full fitting on validated connected paths.
- **200%**: longer smoothing along those same paths.

A source guard only marks where to look. Actual darker, two-sided source profiles must form a connected centerline at least 12 native pixels long, with real spatial extent. Chains split at junctions; short attached spurs are pruned. Small independent dashes stay unfitted. Samples cannot jump to another path, and their positions along the traced chain must be locally compatible. Ink RGB comes from native pixels on that path.

The trace also gates the old source copy-back. Unsupported pixels in the wide source guard stay on the clean quarter/half/full pyramid rather than restoring native texture. Filled features such as the nose, their nearby rims, and junctions are excluded from thin-stroke fitting. Their existing pixels are not rebuilt as guessed lines. This replaces V2.17's median cleanup.

Use **100% / 200% / 400% result zoom** and drag to pan. The line preview still blends cached pixels; moving its strength reruns neither denoising nor tracing/fitting. Higher powers do not lower the path-validation threshold.

**Save live test** exports the original wide-preservation base (`00_original_preservation_base.png`), traced 0% (`01_reconstruction_off.png`), selected result, 200%, full inputs, accepted-path/filled-region/copy-back masks and settings. **Save maps** includes exact native path IDs and signed source-preservation/fitting comparisons. This is a real processing change; the maps explain where it applied.

Other cleanup/color settings require Prepare again. Normal Run and previous comparison buttons retain their existing processing. Missing source evidence, unusually tangled true strokes and very small details can still limit the result; this is geometric tracing, not semantic recognition. See [V2.18 validation](docs/VALIDATION_V218.md).

## Compare line borders on the preferred pyramid

Load your usual pair and keep source-line tracing enabled. Choose **Compare line borders**. It produces `01_pyramid_v213.png` and `02_clean_line_borders.png` from one fixed pyramid, with the same global colors and stroke cleanup/AA off. The border candidate is applied at full strength; there are no extra settings to tune for this test.

The old source-line mask includes paint outside the ink and copies that paint back into the reconstructed image. This experiment measures darker ink profiles separately and estimates adjacent paint from the clean coarse field on the same side of each stroke. It cleans paint closer to ink and removes off-color contamination from partially covered edge pixels, while retaining measured ink and stronger coverage. Old wide-core paint pixels are intentionally allowed to change.

Check the bib pocket, waist seams, faint strokes and opposite sides of outlines. Full inputs/results, native crops, measured-ink/change maps and `share_line_border_test.zip` are exported. Tight gaps and ambiguous shapes can retain fringe; low-coverage details can also be mistaken for paint. The normal Run and existing reconstruction comparison are unchanged. See [line-border validation](docs/VALIDATION_V214.md).

## Compare reconstruction and solid colors

Load your usual pair and keep your usual denoiser and cleanup settings. Choose **Compare reconstruction**. The experiment uses full-strength candidates and turns stroke cleanup and AA off for every comparison image. It exports:

1. `01_accepted.png` — accepted V2.12 cleanup.
2. `02_pyramid.png` — independently cleaned quarter/half layers reconstructed to full size with boundary guidance.
3. `03_hard_colors.png` — one solid color per detected paint region.
4. `04_hard_with_gradients.png` — solid regions with independently supported smooth color trends.

All four use the same fitted global RGB correction. If that fit is unreliable, all four retain source colors; a spatial Classic correction would invalidate the solid-color experiment. Normal Run's color controls and fallback remain unchanged.

Inspect the tree, tail markings, beach sparkles and smoke in the full outputs and native crops. `share_reconstruction_test.zip` includes full inputs/results and additional evidence within a 30-MiB budget. These are experimental comparisons, not a replacement default. The gradient test can reject genuine color variation or accept an artifact; it does not recognize iridescence. See [reconstruction validation](docs/VALIDATION_V213.md).

## Restored clean color correction

Choose **Robust global** for normal Run. It again applies only the fitted RGB transform to the fully cleaned image. The failed V2.11 shading-restoration pass has been removed, including its normal and comparison paths. It no longer transfers variation from the earlier cleanup baseline into the result.

**Compare colors** exports `01_classic.png` and `02_robust_global.png` from the same cleaned image with strokes/AA off. Additional native crops cover the tree, foreground thigh and tail. `share_color_test.zip` retains the full inputs and outputs within the existing budget.

Normal Run retains the V2.12 baseline, including its foreground-tree shading limitation. The new reconstruction comparison is separate from that accepted processing. See [V2.12 regression validation](docs/VALIDATION_V212.md).

## Test stroke cleanup at full strength

Keep your preferred denoiser, cleanup and color method settings (choose **Robust global** for the V2.9 color correction). Choose **Compare strokes 0 / 60 / 100**. It runs the upstream processing once, fits colors once, and compares one full stroke candidate at those three strengths with AA off. Full images, native crops, actual application/change maps and `share_stroke_test.zip` are exported.

For normal Run, enable **Stroke cleanup**. Its strength starts at **100**, which applies the full candidate without extra confidence attenuation. It uses the image's actual local RGB stroke colors; it does not repaint everything black. Short strokes reject background samples so blue gaps between stitches remain gaps. The stronger setting can make ink heavier or alter narrow details; this is an experimental restoration feature.

After a normal Run, **Preview strokes on last result** lets you try strengths without rerunning BM3D or color correction. Repeated previews start from the same post-color pixels. Disable strokes and AA, then preview strokes to recover those exact pixels. Other upstream control changes require Run / Preview.

Stroke cleanup starts disabled for normal processing. The comparison always includes 100 even when the checkbox is off. See [stroke validation](docs/VALIDATION_V210.md).

## Color and AA controls

1. Load your usual pair and choose **Compare colors**. It runs cleanup once, then exports Classic and Robust global with AA off, plus a compact `share_color_test.zip`.
2. For normal Run, select **Robust global** to try the new color method. It learns one global channel transform and falls back to Classic when the fit is unreliable. It does not copy reference geometry or a reference grid into the output.
3. For optional restoration finishing, enable **Optional edge antialiasing** (start at 35), then use **Preview AA on last result**. Turn it off and preview again to restore the exact pre-AA pixels. This preview reuses the last run; other control changes need Run / Preview.

Compare colors and Compare auto keep stroke cleanup and AA off to isolate their original tests. See [V2.9 color validation](docs/VALIDATION_V29.md). Forge integration and intentional per-loop lighting progression are deferred.

## Where the files live

| Location | Purpose |
| --- | --- |
| `stable_shift/` | Active app, denoisers, automatic control, source protection, palette/edit processing and exports |
| `docs/` | User guide and cleanup notes; source checkouts also include processing validation |
| `tests/` | Regression and desktop integration checks in the source checkout |
| `tools/` | Optional maintenance; source checkouts also include historical comparison/replay tools and the ZIP builder |

The two `difference_guard_*` modules inside `stable_shift/` are active color/Edit replacement dependencies. Historical line/blotch comparison wrappers have been removed from the desktop app; the corresponding developer tools remain outside the runtime package. Legacy manual comparison and Preserve Edits remain under Advanced / legacy.

See the [user guide](docs/STANDALONE.md) for controls, themes, drag/drop and diagnostics, or [cleanup notes](docs/CLEANUP.md) for maintenance and developer commands.
