# Stable Shift

Standalone cleanup and color restoration for Stable Diffusion outputs. **V2.11** retains the successful global RGB color fit while restoring source shading contrast that Classic preserved better. Denoising, optional stroke cleanup and AA are unchanged. No new dependencies.

Double-click **START_Stable_Shift.bat**. Load or drop your reference and edited image, then use Run / Preview. Automatic strength starts enabled; source geometry always comes from the edited image. The reference supplies colors only.

## Updating an existing folder

For a Git checkout, close the app and pull the branch you are testing with Git Bash. Git handles tracked file removals; no cleanup script is needed. Keep using **START_Stable_Shift.bat**. The existing `.venv` is reused; this version adds no dependencies.

For a fresh ZIP installation, extract into a new folder and use the Start launcher. It installs base requirements; optional CPU/GPU BM3D can be installed with the app buttons. For older installations updated by copying a ZIP over existing files, see [cleanup notes](docs/CLEANUP.md). `python app.py` remains supported.

## Test color and shading contrast

Choose **Compare colors**. It runs cleanup once and exports:

- `01_classic.png`: unchanged Classic correction.
- `02_robust_previous.png`: the exact previous RGB transform.
- `03_robust_global.png`: that same RGB fit with source lightness contrast restored.

Compare 02 against 03, especially at the foremost tree's roots. Strokes and AA are off throughout. A fourth native crop covers the left background; `share_color_test.zip` includes all full outputs and inputs within the existing size budget. Normal Run with **Robust global** uses 03's behavior.

The fix adjusts supported lightness contrast while retaining the new color fit and broad lighting. It uses alternate renderings of the same cleaned image, not reference texture or geometry. See [V2.11 validation](docs/VALIDATION_V211.md).

## Test stroke cleanup at full strength

Keep your preferred denoiser, cleanup and color method settings (choose **Robust global** for the V2.9 color correction). Choose **Compare strokes 0 / 60 / 100**. It runs the upstream processing once, fits colors once, and compares one full stroke candidate at those three strengths with AA off. Full images, native crops, actual application/change maps and `share_stroke_test.zip` are exported.

For normal Run, enable **Stroke cleanup**. Its strength starts at **100**, which applies the full candidate without extra confidence attenuation. It uses the image's actual local RGB stroke colors; it does not repaint everything black. Short strokes reject background samples so blue gaps between stitches remain gaps. The stronger setting can make ink heavier or alter narrow details; this is an experimental restoration feature.

After a normal Run, **Preview strokes on last result** lets you try strengths without rerunning BM3D or color correction. Repeated previews start from the same post-color pixels. Disable strokes and AA, then preview strokes to recover those exact pixels. Other upstream control changes require Run / Preview.

Stroke cleanup starts disabled for normal processing. The comparison always includes 100 even when the checkbox is off. See [stroke validation](docs/VALIDATION_V210.md).

## Color and AA controls

1. Load your usual pair and choose **Compare colors** for the Classic / previous RGB / restored-shading comparison above.
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
