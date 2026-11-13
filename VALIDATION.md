# V2.0 validation

## Automated checks

`DISPLAY=:99 OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 python -m pytest -q`:

**23 passed, 1 skipped.** The skipped check requires a historical real-image fixture that is not available in this executor; it is not counted as a real-image success.

Checks cover:
- Legacy size handling, Preserve Edits registration safeguards, boundary denoising and actual CPU BM3D noise reduction.
- Explicit GPU dependency failure without silent CPU fallback.
- Cleanup off returns the input exactly before color correction.
- Cleanup visibly changes synthetic low-amplitude variation and reduces error against synthetic ground truth.
- A one-pixel window frame prevents samples mixing two otherwise similar surfaces.
- Synthetic diagonal stitching and a sharp cel-shading boundary remain intact.
- A broad neighborhood suppresses constructed broad chroma variation more than a fine-only neighborhood.
- No structural dependence on the reference when palette matching is off, including differently sized references.
- Separate luminance control, tiny image shapes and invalid-setting rejection.
- Tcl file-list parsing for spaces, braces, Unicode, file URIs, multiple files and folder rejection.
- Actual Tk/tkdnd-registered callback invocation loads each input independently, refuses replacements while busy, and respects theme changes.
- GUI background processing and PNG/settings saving retain the actual run settings after sliders change.
- Comparison PNGs, native crop sheets, diagnostic maps, sizes and per-run metadata.

## Desktop verification

A headless X server was started in the executor. The actual interface and native tkdnd 2.10.3 extension loaded with Tcl/Tk 9, and the layout was visually inspected in dark mode. Both Dark/Light preview backgrounds were exercised. The drop integration checks invoke the registered Tcl callbacks with native DnD arguments, not a physical drag from Windows Explorer. Windows Explorer end-to-end drops and Windows registry theme switching still need local testing.

## Synthetic 2K processing

A 2048×2048 two-surface image with a thin separating frame and added RGB noise was processed with V2 alone, strength 75, LAB range 12, luminance 60, radius 16 and diagnostics enabled:

- Cleanup time: 5.94 seconds.
- Changed pixels: 99.08%.
- Mean absolute RGB change: 1.70/255.
- Protected pixels: 0.29%.
- Peak process RSS: approximately 1.1 GiB, including synthetic generation.

These figures establish execution and a nonzero cleanup effect; they do not measure restoration quality on the user's illustration. No claim is made that V2 beats BM3D on the supplied artwork. Original inline artwork is not available as a local image fixture in this executor. GPU BM3D is unchanged but was not executed here.
