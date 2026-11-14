# Standalone layout and maintenance

This document describes the layout cleanup completed before V2.9. Accepted V2.8 denoising remains unchanged; V2.9's optional color and AA additions are documented in the [standalone guide](STANDALONE.md).

## Existing installations

For Git checkouts, pull the branch you are testing. Git removes tracked obsolete files; the helper below is unnecessary.

Only for older folders updated by copying ZIP contents: copy the extracted update contents into the existing app folder, beside its current `app.py`, and run `CLEANUP_OLD_FILES.bat`. It invokes the bundled maintenance helper using that folder's Python environment, or the Python launcher if no environment exists yet. The new package and launcher must be present before any file can move.

Only a fixed list of known old root filenames is eligible. Each is moved into `_legacy_backup/<timestamp>/`. A JSON manifest records exact names, byte counts, SHA-256 hashes and the files actually moved. Modified versions of those known scripts are preserved in the backup too. To undo a move, copy the file from the backup to the app root after checking that it will not overwrite a newer file.

The helper leaves `.venv`, input images, saved results, settings, comparison exports and unrecognized custom files in place. It does not remove older folders or run automatically during normal startup. Running it again after cleanup does not create another empty backup.

Advanced preview without moving files:

```console
python -m tools.tidy_legacy_files
python -m tools.tidy_legacy_files --apply
```

The first command lists eligible files. The second performs the same backup operation as the Windows cleanup launcher.

## Active application

`python -m stable_shift` and the Start launcher use the package entry point. The small root `app.py` also remains a compatible launch entry point. The project-level `.venv` and `startup.log` retain their original locations.

Active runtime imports use the package namespace. Old root modules cannot accidentally supply the active engine, palette, masks or UI. The visible Run, Compare auto, Legacy manual, Save PNG, Save maps, theme and drag/drop paths remain. Two unbound historical comparison methods and their unused completion handlers were removed from the UI.

`stable_shift/difference_guard_core.py` still supplies the inherited color matcher and registered edit replacement. `difference_guard_multimap.py` is imported by that edit path. Their old names do not mean they are unused.

## Developer checkout

Run checks from the project root:

```console
python -m pytest -q
python -m tools.validate_handoff --help
python -m tools.validate_blotch_pair --help
python -m tools.build_standalone
```

The optional handoff/replay CLIs and historical line/blotch comparison exporters live in `tools/`; the GUI does not import them. Tests retain coverage of their underlying behavior. Developer code should import `stable_shift.engine`, `stable_shift.automatic_strength` and related modules instead of old root module names.

The builder writes `dist/Stable-Shift-v2.9.zip`. The ZIP includes the runtime package, launchers, base requirements, user documentation and the small backup helper. It excludes tests, historical comparison/replay tools, the builder itself, virtual environments, caches and generated/user images. ZIP timestamps and ordering are fixed so rebuilding the same inputs produces identical bytes.

## Verification of the earlier layout cleanup

**85 tests passed, 1 historical-fixture test skipped** after relocation, including the native desktop checks. Additional checks exercise package/root launch entry points, startup-log location, the archive in an isolated directory and reversible old-file migration. Processing functions are compared with the accepted V2.8 source after normalizing only internal import names. Full-resolution CPU stage replays of the beach, cabin and alley retained the accepted output bytes with zero changed RGB pixels. All 12 processing/export modules matched the accepted V2.8 ASTs after normalizing package import names. The small standalone ZIP contains 24 files and runs from an isolated extraction without developer scripts.

The Windows batch launchers retain the existing environment setup and dependency-installation commands. Native Windows execution and GPU hardware are not available in this Linux environment; the GPU adapter is unchanged.
