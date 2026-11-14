# Stable Shift

Standalone cleanup and color restoration for Stable Diffusion outputs. **V2.9** retains the accepted V2.8 denoising and adds an optional global color matcher and optional finishing antialiasing. Classic color correction remains the default; AA starts off.

Double-click **START_Stable_Shift.bat**. Load or drop your reference and edited image, then use Run / Preview. Automatic strength starts enabled; source geometry always comes from the edited image. The reference supplies colors only.

## Updating an existing folder

For a Git checkout, close the app and pull the branch you are testing with Git Bash. Git handles tracked file removals; no cleanup script is needed. Keep using **START_Stable_Shift.bat**. The existing `.venv` is reused; this version adds no dependencies.

For a fresh ZIP installation, extract into a new folder and use the Start launcher. It installs base requirements; optional CPU/GPU BM3D can be installed with the app buttons. For older installations updated by copying a ZIP over existing files, see [cleanup notes](docs/CLEANUP.md). `python app.py` remains supported.

## Test colors and AA separately

1. Load your usual pair and choose **Compare colors**. It runs cleanup once, then exports Classic and Robust global with AA off, plus a compact `share_color_test.zip`.
2. For normal Run, select **Robust global** to try the new color method. It learns one global channel transform and falls back to Classic when the fit is unreliable. It does not copy reference geometry or a reference grid into the output.
3. For optional restoration finishing, enable **Optional edge antialiasing** (start at 35), then use **Preview AA on last result**. Turn it off and preview again to restore the exact pre-AA pixels. This preview reuses the last run; other control changes need Run / Preview.

See [V2.9 validation](docs/VALIDATION_V29.md) for checks and limits. Forge integration and intentional per-loop lighting progression are deferred.

## Where the files live

| Location | Purpose |
| --- | --- |
| `stable_shift/` | Active app, denoisers, automatic control, source protection, palette/edit processing and exports |
| `docs/` | User guide and cleanup notes; source checkouts also include processing validation |
| `tests/` | Regression and desktop integration checks in the source checkout |
| `tools/` | Optional maintenance; source checkouts also include historical comparison/replay tools and the ZIP builder |

The two `difference_guard_*` modules inside `stable_shift/` are active color/Edit replacement dependencies. Historical line/blotch comparison wrappers have been removed from the desktop app; the corresponding developer tools remain outside the runtime package. Legacy manual comparison and Preserve Edits remain under Advanced / legacy.

See the [user guide](docs/STANDALONE.md) for controls, themes, drag/drop and diagnostics, or [cleanup notes](docs/CLEANUP.md) for maintenance and developer commands.
