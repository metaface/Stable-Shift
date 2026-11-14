# Stable Shift

Standalone cleanup and color restoration for Stable Diffusion outputs. This layout retains the accepted **V2.8 image processing**.

Double-click **START_Stable_Shift.bat**. Load or drop your reference and edited image, then use Run / Preview. Automatic strength starts enabled; source geometry always comes from the edited image. The reference supplies colors only.

## Updating an existing folder

1. Close the app, then copy the contents of the extracted update into your existing app folder, beside its current `app.py`, so its `.venv` stays available.
2. Run **CLEANUP_OLD_FILES.bat** once. It moves known old root scripts and launchers into `_legacy_backup/<timestamp>/`, with an exact file manifest. Your installed environment, images, outputs and unrecognized custom files stay in place.
3. Start the app with **START_Stable_Shift.bat** from now on. `python app.py` remains supported.

For a fresh installation, extract into a new folder and use the Start launcher. It installs the base requirements; optional CPU/GPU BM3D can be installed with the existing app buttons.

## Where the files live

| Location | Purpose |
| --- | --- |
| `stable_shift/` | Active app, denoisers, automatic control, source protection, palette/edit processing and exports |
| `docs/` | User guide and cleanup notes; source checkouts also include processing validation |
| `tests/` | Regression and desktop integration checks in the source checkout |
| `tools/` | Optional maintenance; source checkouts also include historical comparison/replay tools and the ZIP builder |

The two `difference_guard_*` modules inside `stable_shift/` are active color/Edit replacement dependencies. Historical line/blotch comparison wrappers have been removed from the desktop app; the corresponding developer tools remain outside the runtime package. The visible Legacy manual comparison and Preserve Edits remain available.

See the [user guide](docs/STANDALONE.md) for controls, themes, drag/drop and diagnostics, or [cleanup notes](docs/CLEANUP.md) for maintenance and developer commands.
