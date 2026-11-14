# Stable Shift V2.5 — standalone test build

## Current test: retain faint source strokes

Keep your accepted V2.4 denoiser, local-cleanup, broad-cleanup and color settings. Leave source-line tracing enabled. Use **Compare lines** to compare the previous tracer with the updated one; the shared denoiser runs once and the same frozen V2.4 palette field is applied to both outputs.

- `00_v24_before_palette.png`: V2.4 tracing/cleanup before color correction.
- `01_faint_lines_before_palette.png`: updated tracing with identical cleanup settings.
- `02_v24_same_palette.png`: V2.4 result with the shared palette field.
- `03_faint_lines_same_palette.png`: updated result with that same field.

Judge 02 versus 03; inspect 00 versus 01 to isolate processing before palette conversion. Both variants run local and broad cleanup separately, because their source barriers differ. Only the backend denoiser result and palette field are shared.

The tracer uses the original edited image. Weaker edge samples can be retained between compatible old trace segments, with anchors in both tangent directions within 12 native pixels. Eight directions follow slanted strokes. Gradient polarity and dominant color channel must match; source coherence and tangent evidence are still required. A newly retained point never supplies an anchor for another point. Points already covered by the old protection band do not widen that band. Original RGB is copied at the denoiser handoff and the updated mask is carried through the existing cleanup stages.

This is not a pen that fills missing strokes. Blank source gaps and unsupported longer gaps remain; originally faint lines and contrast compressed by palette conversion may still look faint. No antialiasing or automatic stroke darkening is applied.

New maps:

- `source_line_trace_base`: V2.4 trace before continuation.
- `source_line_rescued`: additional observed weak source edge points.
- `source_line_added_core`: additional protection only.

Existing `source_line_trace` and `source_line_core` include the added protection. The comparison saves `v24_` and `v25_` maps, plus settings/timings and checks on previous/new source cores. Signed stage maps include the actual shared palette application and still sum to total change.

**share_line_test.zip** is the file to upload for feedback. It includes all four full-size outputs, `edited_source.png`, source masks and settings. Large diagnostic NPZ files and extra previews are excluded. The original edited RGB is included so subsequent source-tracer tests can use the actual input. If those full-resolution files exceed 30 MiB together, individual files are retained and the report records why no compact ZIP was created.

Run/Preview enables faint continuity by default. Its palette field is fitted normally from its own pre-broad local-cleanup result. The comparison freezes the V2.4 baseline field to isolate line retention, so a small difference between the normal preview and its controlled comparison is possible. Advanced/API users can select the previous tracer with `Options(faint_continuity=False)`.

## Current focus: local blotch correction

V2.4 revises the extra V2.3 blotch stage. V2.1 source-line tracing, local cleanup, color estimation, edit replacement, BM3D adapters and dependencies are retained. The unmerged V2.2 palette experiment is excluded.

### Retained V2.4 surface cleanup

The V2.4 blotch pass is retained without algorithm or default changes. The new toolbar comparison targets line protection; keep whichever broad strength you preferred. The older blotch-comparison export remains available through its Python module.

The shared BM3D/local-cleanup baseline runs once. Compare these native-resolution outputs:

- `00_v21_before_palette.png`: shared V2.1 baseline before color correction.
- `01_broad_before_palette.png`: baseline plus the revised local blotch pass.
- `02_v21_same_palette.png`: baseline with its V2.1 palette field.
- `03_broad_same_palette.png`: local blotch correction with the EXACT same field.

Judge 02 versus 03; 00 versus 01 isolates cleanup. Crop sheets use identical coordinates. The legacy Compare V2 workflow leaves broad correction off. Strength 0 is an exact bypass in Run/Preview.

### How the revised pass works

1. The existing boundary graph and original source core partition free interiors. Small regions below 128 pixels stay unchanged.
2. A robust regional trend detrends the samples. Local, mask-normalized residual smoothing at native resolution adds wider shading back, rather than replacing the region with that trend. Separate regions do not share samples.
3. Local variation, fine scatter and fit consistency set the automatic correction amount. A high similarity range cannot disable the independent heterogeneity limit.
4. Correction fades smoothly beside protected boundaries. Requested moves are capped at 3 LAB units before conversion; output RGB channels stay inside the observed 49×49 source neighborhood envelope.
5. The shared V2.1 palette field is fitted from the pre-broad baseline and applied last to both variants.

The existing Brightness cleanup control scales the extra pass's L correction too. The local radius still controls only V2.1's local sampler; the extra stage uses a fixed 32-pixel residual sigma. No new scale controls are introduced in this test.

**Auto** describes the extra blotch stage's local strength estimate. Existing BM3D noise strengths and local-cleanup settings are still manual. This does not understand artistic intent; intentional texture may be softened, broad contamination may remain, and protected fringes/sparkle halos are not specifically removed.

### Diagnostics and reporting

- `blotch_boundaries`: actual excluded pixels; white means excluded.
- `blotch_boundary_taper`: gradual correction fade; 0 = none, 1 = full allowed amount.
- `blotch_automatic_amount`: local confidence-limited strength before luminance scaling and final bounds; not a probability that a pixel is noise.
- `blotch_fit_error`: local target residual divided by the configured LAB range.
- `blotch_change` / `blotch_signed_rgb`: the extra stage only, before palette correction.
- `local_cleanup_change` / `local_cleanup_signed_rgb`: retained V2.1 local cleanup only.

Comparison reports include exact protected-pixel changes before/after the shared palette, plus change immediately beside the core. Unchanged stroke pixels alone do not prove that a stroke keeps its contrast. Raw maps retain native values; previews use fixed legend scales.

See [VALIDATION.md](VALIDATION.md) for the supplied comparison replay, synthetic controls, full-resolution beach control, timing and limitations. The optional `validate_blotch_pair.py` replays exported pre-palette pairs without BM3D; normal use is through the launcher and Compare lines.

## V2.1 source-line correction (retained)

Leave **Trace source lines before denoising and protect them through cleanup** on for the new behavior. Turning it off restores the V2.0 guard/cleanup behavior for comparison.

The original edited image's hard and soft evidence is computed once, before denoising. Supported weaker segments can link to a strong seed or survive as a sufficiently long coherent line of their own. Directional continuity, a high-frequency scatter estimate and a small component filter reduce isolated grain. A one-pixel support band retains a stroke center between its detected sides.

Those traced source pixels are kept at the denoiser handoff and the SAME mask is passed into the cleanup boundary graph. It closes sampling links even where the processed image's local gradient is now too weak. Source-protected pixels retain original edited RGB through denoising/cleanup, before final palette correction. This is not a semantic line/noise classifier; some real details can be missed and some noise can be preserved.

The CPU/GPU BM3D implementations are unchanged and still do not accept a custom internal boundary map. New source preservation happens at their handoff, not within BM3D's patch processing. Internal boundary constraints apply to V2's own neighborhood sampling.

With tracing on and a denoiser selected, Compare V2 now exports four runs: legacy baseline, source protection only, source protection plus surface cleanup, and protected surface cleanup alone. With tracing off it retains three runs. In Region cleanup only/Color only modes it retains the palette baseline and surface-only comparison. The same settings and color correction apply to every run, with only the named features changed. The original legacy hard/soft guard sliders remain active in the baseline; compare against identical V2.0 settings.

## Reading the corrected maps

Save maps and comparison exports now contain:

- `source_line_core.png`: black/white actual source protection, not a weak colored confidence preview. White is preserved through the handoff and passed to cleanup.
- `source_line_confidence`, `source_line_candidates`, `source_line_seeds`, `source_line_trace`: evidence and linking diagnostics.
- `v2_boundaries.png`: actual cleanup exclusions, combining carried source lines with locally detected boundaries. White pixels are excluded from cleanup.
- `denoise_change`, `cleanup_change`, `palette_change`, `total_change`: separate magnitudes, all at a fixed 0–16 RGB-level display range. The legacy `difference` key remains total change at its older 0–70 range; use the stage maps instead.
- `diagnostics_raw.npz`: exact native-resolution arrays, including signed `denoise_signed_rgb`, `cleanup_signed_rgb`, `palette_signed_rgb` and `total_signed_rgb`. Values are int16 **after minus before**. The three stage residuals sum exactly to the total residual.
- Signed previews: R/G/B channels shown separately, blue for negative, gray for zero and orange for positive, saturating at +/-16. Previews may be resized; raw arrays retain full values and resolution.
- `MAP_LEGEND.png` / `.md`: units and map roles.

Heatmap blue/green/red colors encode magnitudes, not the original color of a blotch. Total change includes global reference palette correction, so a bright region does not establish that all its variation is noise. Cleanup changes are measured before palette correction. The per-scale differences remain heuristic reconstruction evidence, not classified noise.

Normal PNG Save still writes the actual run settings/timings JSON. Maps/NPZ are exported only through Save maps or Compare. Raw map exports can use substantial disk space at 2K/4K; export time is not included in each run's processing timer.

## CuPy CUDA-path warning

A console `UserWarning: CUDA path could not be detected` is not a traceback or an unfinished installation by itself. If GPU BM3D finishes, the adapter actually executed GPU operations and synchronized them; it did not silently run CPU BM3D. No guessed CUDA_PATH, driver install or blanket warning suppression is applied by V2.1. If GPU execution fails, retain the full error, since runtime/driver troubleshooting depends on that failure rather than this warning alone.

## Installation and drag/drop

Extract outside Forge. Use a 64-bit Python installation with Tkinter; Python 3.11/3.12 are recommended for optional BM3D dependencies. Start with `START_Difference_Guard.bat`, not by directly opening app.py. Base dependencies include `tkinterdnd2==0.7.0`, which bundles native Tk drag/drop support, including Tcl/Tk 9 support. The launcher upgrades an older installed tkinterdnd2 automatically. Internet is needed for initial installation or dependency upgrades; normal launches with dependencies present do not run pip.

Drop one image file onto either input panel; the panel, its image canvas, and its Open button accept file drops. Spaces, braces and Unicode in paths are parsed as a Tcl file list, not split on spaces. Multiple files in one drop are rejected instead of guessing which image you meant. Inputs cannot be replaced during processing, and replacing an input clears the old result to prevent saving a stale image. File dialogs remember the last directory separately for each slot.

If the native Tk extension fails to load, Open buttons remain usable and the app explicitly labels drag/drop unavailable. The failure is recorded in startup.log. Windows Explorer may not drag into an app launched with elevated privileges; launch normally, not as Administrator.

A new extracted folder has its own `.venv`; optional CPU/GPU BM3D must be installed there using the app buttons. Updating files in your existing V1.1 folder reuses its environment and backend installations. Keep a backup of that folder first if you choose to update in place. Do not copy live virtual environments between machines.

## Controls and initial comparison

- **Denoiser:** GPU/CPU BM3D retain the V1.1 adapter. NLM and Boundary constrained remain available as legacy comparisons. Region cleanup only skips those denoisers; Color only skips them too, and is truly palette-only when Surface cleanup and Broad correction maximum are both 0.
- **Luminance/Color denoise:** existing denoiser strengths. They do not set V2 surface cleanup strength.
- **Surface cleanup:** 0 bypasses V2 exactly before palette correction; 100 applies its complete estimated correction. Start at 60. This is the replacement for the ineffective V1.1 chroma-only finishing pass.
- **Brightness cleanup:** how much luminance cleanup accompanies chroma cleanup. Start at 60; 0 keeps LAB lightness unchanged during cleanup, apart from small RGB round-trip/gamut effects. Unlike V1.1, default cleanup can affect gray brightness texture too.
- **Color similarity range:** approximate LAB distance for compatible neighbors. Start at 12. Increasing to 16–20 accepts more variation but can also remove subtle real shading or texture. Lower it if details weaken. It also influences the automatic boundary threshold, so it is not simply a strength multiplier.
- **Broad radius:** native-resolution sample reach, 2–32 pixels. Start at 16. Larger values can address wider variations; very broad contamination may remain. Smaller values are cheaper and more local.
- **Reference color correction:** inherited global LAB matcher, applied last. V2 does not claim to solve its remaining cream-fur/muted-denim bias. Turn it off to isolate cleanup when evaluating maps or noise.
- **Advanced / legacy:** reveals existing hard/soft guards and shading sensitivity for legacy denoisers, plus the unchanged Preserve Edits task. V2 has its own boundary graph controlled by color similarity; the hard/soft legacy guard sliders do not control it. Original shading-boundary sensitivity also affects the source evidence used by V2.1 tracing.

Select GPU BM3D and choose **Compare V2** with Surface cleanup above 0. With source tracing off, the retained V2 comparison exports:

1. Selected denoiser with V2 off.
2. The same denoiser with the current V2 settings.
3. V2 alone on the edited image.

No backend is silently substituted. If you select Region cleanup only or Color only, comparison instead exports a palette-only baseline and V2 alone; it does not unexpectedly start a slow CPU BM3D run. Each comparison gets a fresh timestamped subfolder. At Surface cleanup 0, use Run to see the baseline; Compare asks you to set a nonzero strength so its variants are meaningful.

Inspect full-resolution PNGs and native-pixel crop sheets, particularly denim, stitches, and the cabin frame. Diagnostic maps include detected boundaries, actual cleanup change, sample support, medium/fine differences, and fine-detail weighting. Maps describe cleanup before the final palette transform. A status line reports the percentage of changed pixels and average RGB change so a visually subtle stage can be diagnosed.

## What the V2 experiment actually does

The image is never reduced to quarter/half size for V2. Instead, it estimates fine (up to radius 2), medium (up to 6) and broad (chosen radius) color fields independently on the full-resolution grid. This preserves the coarse-to-fine roles discussed without destroying thin lines through ordinary downsampling.

1. When tracing is on, carry the original source-line core into the graph. Also build horizontal/vertical boundary links from lightly guided color differences and strong native-resolution jumps. Require aligned support to avoid treating every isolated grain pixel as a line. Diagonal links cannot cut through closed horizontal/vertical corners. This is automatic local structure detection, not object segmentation.
2. Sample in eight directions at a sparse set of distances. A candidate must be within the target pixel's LAB color range **and** the entire straight path to it must avoid blocked links. No chaining of nearby colors into a different surface is used.
3. Form normalized, Tukey-weighted local surface estimates at all three scales. Protected boundary pixels are not eligible for correction.
4. Reconstruct broad → medium difference → fine difference. Distance from boundaries selects how much finer information returns. It is a heuristic residual gate, not a learned noise/detail classifier.
5. Apply cleanup strength and independent lightness strength, then optional reference color correction.

The small guide blur is used to *detect* boundaries, never as an output color layer. The V2 operation does not run an unconditional blur and repair contours afterward. BM3D/NLM still retain their inherited post-denoiser edge blending; their internal algorithms have not been modified to accept custom barriers.

This is a testable approximation of region-aware multiscale reconstruction. Sparse directional sampling may leave texture, miss broad patches, or introduce directional artifacts. Misdetected boundaries can trap noise or expose weak detail. It does not identify artistic intent and does not transfer reference geometry or texture. Check whether it actually improves your real image before preferring it over GPU BM3D alone.

## Timing, hardware and scope

Live elapsed time and completed per-stage timings remain. Save PNG also saves its actual run settings/timings, even if controls changed afterward. Timings exclude image loading, preview rendering and file export; the first GPU run can include CUDA setup/compilation.

GPU BM3D uses `bm3d-cupy[cuda12]==0.1.3`; CPU BM3D uses `bm3d==4.0.3`. The V2 cleanup itself runs on CPU NumPy/OpenCV and is timed separately. A synthetic 2048×2048 cleanup run at strength 75, LAB range 12, lightness 60 and radius 16 took about 5.94 seconds in the development executor, with approximately 1.1 GiB peak process memory including synthetic-image generation and diagnostics. This is not a benchmark of your RTX 5080 or real image.

The GPU adapter is unchanged from the version you tested successfully. V2.1 adds original-source analysis and separate diagnostic timing to the processing report. GPU execution is not available in this development environment. If it fails, the app reports the error and leaves CPU BM3D available; it does not silently fall back. No neural model, semantic restoration, negative-clarity luminance model, Forge integration or Preserve Edits mask improvement was added.

System/Dark/Light themes are retained. On Windows System follows AppsUseLightTheme; other systems default to dark if detection is unavailable. Native dialogs use the OS's own theme.

License references for optional backends:
- https://pypi.org/project/bm3d/ (published noncommercial CPU package terms)
- https://pypi.org/project/bm3d-cupy/
- https://github.com/kvttt/bm3d_cupy

## Developer checks

Install the basic requirements, CPU BM3D and pytest in a development environment, then run `python -m pytest -q`. UI checks require an available display on Linux. Dependencies and virtual environments are not committed.
