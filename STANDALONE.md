# Stable Shift V2.0 — standalone test build

## Installation and drag/drop

Extract outside Forge. Use a 64-bit Python installation with Tkinter; Python 3.11/3.12 are recommended for optional BM3D dependencies. Start with `START_Difference_Guard.bat`, not by directly opening app.py. Base dependencies include `tkinterdnd2==0.7.0`, which bundles native Tk drag/drop support, including Tcl/Tk 9 support. The launcher upgrades an older installed tkinterdnd2 automatically. Internet is needed for initial installation or dependency upgrades; normal launches with dependencies present do not run pip.

Drop one image file onto either input panel; the panel, its image canvas, and its Open button accept file drops. Spaces, braces and Unicode in paths are parsed as a Tcl file list, not split on spaces. Multiple files in one drop are rejected instead of guessing which image you meant. Inputs cannot be replaced during processing, and replacing an input clears the old result to prevent saving a stale image. File dialogs remember the last directory separately for each slot.

If the native Tk extension fails to load, Open buttons remain usable and the app explicitly labels drag/drop unavailable. The failure is recorded in startup.log. Windows Explorer may not drag into an app launched with elevated privileges; launch normally, not as Administrator.

A new extracted folder has its own `.venv`; optional CPU/GPU BM3D must be installed there using the app buttons. Updating files in your existing V1.1 folder reuses its environment and backend installations. Keep a backup of that folder first if you choose to update in place. Do not copy live virtual environments between machines.

## Controls and initial comparison

- **Denoiser:** GPU/CPU BM3D retain the V1.1 adapter. NLM and Boundary constrained remain available as legacy comparisons. Region cleanup only skips those denoisers; Color only skips them too, and is truly palette-only when Surface cleanup is 0.
- **Luminance/Color denoise:** existing denoiser strengths. They do not set V2 surface cleanup strength.
- **Surface cleanup:** 0 bypasses V2 exactly before palette correction; 100 applies its complete estimated correction. Start at 60. This is the replacement for the ineffective V1.1 chroma-only finishing pass.
- **Brightness cleanup:** how much luminance cleanup accompanies chroma cleanup. Start at 60; 0 keeps LAB lightness unchanged during cleanup, apart from small RGB round-trip/gamut effects. Unlike V1.1, default cleanup can affect gray brightness texture too.
- **Color similarity range:** approximate LAB distance for compatible neighbors. Start at 12. Increasing to 16–20 accepts more variation but can also remove subtle real shading or texture. Lower it if details weaken. It also influences the automatic boundary threshold, so it is not simply a strength multiplier.
- **Broad radius:** native-resolution sample reach, 2–32 pixels. Start at 16. Larger values can address wider variations; very broad contamination may remain. Smaller values are cheaper and more local.
- **Reference color correction:** inherited global LAB matcher, applied last. V2 does not claim to solve its remaining cream-fur/muted-denim bias. Turn it off to isolate cleanup when evaluating maps or noise.
- **Advanced / legacy:** reveals existing hard/soft guards and shading sensitivity for legacy denoisers, plus the unchanged Preserve Edits task. V2 has its own boundary graph controlled by color similarity; these legacy edge sliders do not control it.

Select GPU BM3D and choose **Compare V2** with Surface cleanup above 0. It exports:

1. Selected denoiser with V2 off.
2. The same denoiser with the current V2 settings.
3. V2 alone on the edited image.

No backend is silently substituted. If you select Region cleanup only or Color only, comparison instead exports a palette-only baseline and V2 alone; it does not unexpectedly start a slow CPU BM3D run. Each comparison gets a fresh timestamped subfolder. At Surface cleanup 0, use Run to see the baseline; Compare asks you to set a nonzero strength so its variants are meaningful.

Inspect full-resolution PNGs and native-pixel crop sheets, particularly denim, stitches, and the cabin frame. Diagnostic maps include detected boundaries, actual cleanup change, sample support, medium/fine differences, and fine-detail weighting. Maps describe cleanup before the final palette transform. A status line reports the percentage of changed pixels and average RGB change so a visually subtle stage can be diagnosed.

## What the V2 experiment actually does

The image is never reduced to quarter/half size for V2. Instead, it estimates fine (up to radius 2), medium (up to 6) and broad (chosen radius) color fields independently on the full-resolution grid. This preserves the coarse-to-fine roles discussed without destroying thin lines through ordinary downsampling.

1. Build horizontal/vertical boundary links from lightly guided color differences and strong native-resolution jumps. Require aligned support to avoid treating every isolated grain pixel as a line. Diagonal links cannot cut through closed horizontal/vertical corners. This is automatic local structure detection, not object segmentation.
2. Sample in eight directions at a sparse set of distances. A candidate must be within the target pixel's LAB color range **and** the entire straight path to it must avoid blocked links. No chaining of nearby colors into a different surface is used.
3. Form normalized, Tukey-weighted local surface estimates at all three scales. Protected boundary pixels are not eligible for correction.
4. Reconstruct broad → medium difference → fine difference. Distance from boundaries selects how much finer information returns. It is a heuristic residual gate, not a learned noise/detail classifier.
5. Apply cleanup strength and independent lightness strength, then optional reference color correction.

The small guide blur is used to *detect* boundaries, never as an output color layer. The V2 operation does not run an unconditional blur and repair contours afterward. BM3D/NLM still retain their inherited post-denoiser edge blending; their internal algorithms have not been modified to accept custom barriers.

This is a testable approximation of region-aware multiscale reconstruction. Sparse directional sampling may leave texture, miss broad patches, or introduce directional artifacts. Misdetected boundaries can trap noise or expose weak detail. It does not identify artistic intent and does not transfer reference geometry or texture. Check whether it actually improves your real image before preferring it over GPU BM3D alone.

## Timing, hardware and scope

Live elapsed time and completed per-stage timings remain. Save PNG also saves its actual run settings/timings, even if controls changed afterward. Timings exclude image loading, preview rendering and file export; the first GPU run can include CUDA setup/compilation.

GPU BM3D uses `bm3d-cupy[cuda12]==0.1.3`; CPU BM3D uses `bm3d==4.0.3`. The V2 cleanup itself runs on CPU NumPy/OpenCV and is timed separately. A synthetic 2048×2048 cleanup run at strength 75, LAB range 12, lightness 60 and radius 16 took about 5.94 seconds in the development executor, with approximately 1.1 GiB peak process memory including synthetic-image generation and diagnostics. This is not a benchmark of your RTX 5080 or real image.

The GPU adapter is unchanged from the version you tested successfully. GPU execution is not available in this development environment. If it fails, the app reports the error and leaves CPU BM3D available; it does not silently fall back. No neural model, semantic restoration, negative-clarity luminance model, Forge integration or Preserve Edits mask improvement was added.

System/Dark/Light themes are retained. On Windows System follows AppsUseLightTheme; other systems default to dark if detection is unavailable. Native dialogs use the OS's own theme.

License references for optional backends:
- https://pypi.org/project/bm3d/ (published noncommercial CPU package terms)
- https://pypi.org/project/bm3d-cupy/
- https://github.com/kvttt/bm3d_cupy

## Developer checks

Install the basic requirements, CPU BM3D and pytest in a development environment, then run `python -m pytest -q`. UI checks require an available display on Linux. Dependencies and virtual environments are not committed.
