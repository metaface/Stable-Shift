# V2.1 validation

## Checks

Linux with a real Tk/tkdnd test display:

`DISPLAY=:99 OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 python -m pytest -q`

**31 passed, 1 skipped.** The skipped check requires a historical real-image fixture that is not available. GPU execution and Windows Explorer end-to-end drag/drop are not verified in this executor.

Retained checks cover actual CPU BM3D noise reduction, explicit GPU dependency failure, size/registration rules, reference independence, V2 cleanup, high-contrast and diagonal boundaries, native Tcl drop callbacks, filename parsing, GUI processing, themes, PNG saving and actual-settings export.

New regressions cover:
- A faint long line can survive source linking without meeting the hard-seed threshold.
- A featureless noisy surface is not mostly classified as protected linework.
- The same original source core is used at the denoiser handoff and in cleanup. Protected source pixels remain exact before palette correction even when a controlled denoiser erases the line.
- Carried source boundaries stop cross-surface sampling when cleanup's local image cannot detect the boundary.
- Denoise + cleanup + palette signed residuals sum exactly to total change.
- Palette-only changes produce zero cleanup residual, preventing total-change maps being misrepresented as noise maps.
- Exported signed int16 arrays retain signs/values; binary protection PNGs use actual black/white values and have legends.
- The comparison plan isolates legacy baseline, source-line protection and surface cleanup.
- The actual GUI Save maps action exports raw arrays, source protection and legends.

## Actual CPU BM3D weak-line exercise

A 192×192 synthetic dark surface with three faint one-pixel horizontal lines, a stronger connected frame and a high-contrast light foreground was processed with actual CPU BM3D, both with and without source tracing. Legacy hard/soft guards were set to 0 in both runs to isolate the new protection; palette correction was off.

At the measured interior of the faint line, baseline mean absolute RGB error was 7/255; source tracing plus cleanup retained original line RGB exactly (0 error), with 100% traced coverage along that measured segment. This is a controlled synthetic regression, not a measurement on the user's cabin illustration.

## 2048×2048 execution

A synthetic two-surface image with a separating line and RGB noise was processed in Region cleanup only mode using a half-sized reference, source tracing on, cleanup 60, LAB range 12, luminance 60 and radius 16. Palette correction was disabled:

- Original source analysis/tracing: 1.28 s.
- Denoiser handoff (no denoiser in this mode): 0.03 s.
- Cleanup: 5.70 s.
- Stage diagnostics: 0.32 s.
- Total processing: 7.33 s, excluding file export and preview rendering.
- Source core: 3.32% of pixels.
- Peak process RSS: approximately 1.29 GiB, including synthetic generation and diagnostics.

These are development-executor figures, not an RTX 5080 benchmark or a claim of superior restoration quality. Original inline artwork is not available locally as an image fixture. The original image remains the color reference only; no reference structure was used.

## Desktop

The V2.1 checkbox and dark preview layout were visually inspected under a test display with native tkdnd 2.10.3 and Tcl/Tk 9. The existing drag/drop bindings, background worker and Save maps flow were exercised. Windows registry theme detection and physical Explorer drops still require user testing.

The CuPy CUDA-path warning is documented; no CUDA_PATH guessing or warning suppression was added. The BM3D adapters are unchanged.
