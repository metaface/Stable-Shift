# Stable Shift

Standalone cleanup and color restoration for Stable Diffusion outputs. **V2.15** adds live line-preservation strength to the preferred quarter-to-half-to-full pyramid with V2.14 border cleanup. Prepare once, then adjust lines without repeating denoising, reconstruction or color fitting. No new dependencies.

Double-click **START_Stable_Shift.bat**. Load or drop your reference and edited image, then use Run / Preview. Automatic strength starts enabled; source geometry always comes from the edited image. The reference supplies colors only.

## Updating an existing folder

For a Git checkout, close the app and pull the branch you are testing with Git Bash. Git handles tracked file removals; no cleanup script is needed. Keep using **START_Stable_Shift.bat**. The existing `.venv` is reused; this version adds no dependencies.

For a fresh ZIP installation, extract into a new folder and use the Start launcher. It installs base requirements; optional CPU/GPU BM3D can be installed with the app buttons. For older installations updated by copying a ZIP over existing files, see [cleanup notes](docs/CLEANUP.md). `python app.py` remains supported.

## Live line-preservation test

Load your usual pair/settings and choose **Prepare live pyramid**. This does the native, quarter and half processing once. Then drag **Line preservation %** or type a value:

- **0%**: exactly the V2.14 cleaned-border result.
- **100%** (initial value): restore darker supported strokes from the edited source.
- **200%**: increase coverage toward nearby observed ink; this can thicken strokes.

Values between the endpoints blend continuously from the same cached pixels. Try 0, 100 and 200 first. Use **Result zoom: 100% / 200% / 400%** and drag the result to inspect faint strokes. Zoom uses nearest-neighbor display so it does not conceal pixel noise. **Fit** shows the whole result. Saved images always retain their full resolution.

The lighter surrounding paint is not copied back with the old wide source mask. This is a test of dark-stroke preservation, not line recognition, antialiasing or invented gap filling. Source ink can itself contain grid damage. High settings may make that damage more visible or thicken small details. It does not recover every lost bright detail or shading boundary.

**Save PNG + timings** records the displayed strength and frozen upstream settings, even if controls were edited afterward. **Save live test** exports the 0% baseline, displayed selection, 200% view, full inputs and settings; a ZIP is created when they fit within 30 MiB. **Save maps** records actual signed line changes relative to the displayed cache's 0% base. No export reruns processing.

Other denoiser/color settings take effect only after **Prepare live pyramid** again. Stroke cleanup and AA are off in this test. Normal **Run / Preview** still uses V2.12 cleanup; earlier comparison buttons remain available. See [live-preview validation](docs/VALIDATION_V215.md).

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
