# Stable Shift V2.6 — standalone test build

## Automatic strength

The new checkbox controls **Restore Quality**. It starts enabled. Luminance denoise, Color denoise, Surface cleanup, Brightness cleanup and Broad correction start at 100 as maximum permitted strengths. Auto selects lower fine-denoiser values and limits local/broad cleanup spatially. Similarity range and neighborhood radius keep their existing meanings and defaults (12 LAB, 16 pixels).

Start with the usual edited image and color reference, source tracing enabled, and Run / Preview. The status describes selected fine strengths or a skipped fine stage, plus average luminance/chroma surface permissions. These averages are not percentages of noise removed. Turning Auto off restores direct manual control. The API retains manual behavior by default: use `Options(auto_strength=True)` to enable the controller.

The controller measures three kinds of source evidence:

1. A robust high-frequency LAB scatter estimate sets the existing fine-denoiser sliders, capped by the requested ceilings. Calibration uses the unchanged BM3D sigma mapping. Legacy NLM/diffusion accept the same bounded slider values but have different strength scales.
2. Medium-scale luminance/chroma variation identifies possible correlated contamination. Extra luminance cleanup requires accompanying colored variation, since gray variation alone can be smoke, shading or deliberate texture.
3. Directional coherence and distance from protected source lines reduce the allowed correction. Zero-weight pixels retain exact input RGB for that stage. The original source core remains protected through both cleanup stages.

Both surface stages still form their V2.4 candidates. Auto limits each candidate's LAB correction independently in luminance/chroma; it adds no new smoothing filter. If both selected fine strengths are zero, it skips the backend rather than imposing BM3D's nonzero manual minimum. The report records the skip reason and reports no applied backend sigma. If only one selected strength is zero, the unchanged backend still applies its minimum in that channel.

This is conservative source analysis, not a learned or semantic classifier. Gray-only coarse blotches, subtle contamination and some protected texture can remain. Intentional colored texture can still be softened. Auto does not repair missing source strokes or guarantee unchanged contrast after color conversion. Repeated passes need not converge to an artistically correct image.

## Controlled comparison

Choose **Compare auto** and a parent folder. It creates `auto_test_v26_<timestamp>` containing:

- `00_manual_before_palette.png`: requested manual strengths, V2.4 tracing/cleanup, before colors.
- `01_auto_before_palette.png`: automatic strengths and limits, before colors.
- `02_manual_same_palette.png`: manual result with the frozen manual-baseline palette field.
- `03_auto_same_palette.png`: automatic result with that exact field.

Judge 02 versus 03; inspect 00 versus 01 if a color difference obscures the cleanup. The source tracer and its settings are identical in both. The accepted V2.4 tracer is the default (`faint_continuity=False`); V2.5's optional faint continuation is retained in the legacy Python comparison and is not part of the new test.

Different selected strengths require separate backend runs. Auto may skip its fine stage. The comparison reports per-run processing and paired palette timing; exports are outside those timers. Normal Run fits the existing palette matcher to its own local-cleanup result. Compare auto freezes the field fitted to the manual local-cleanup baseline, so its automatic final image can differ from a normal Run preview. With reference correction off, neither variant receives a palette transform.

The folder includes `edited_source.png`, `color_reference.png`, common `source_protection.png`, raw denoiser images, settings/timings, stage maps, native crops and a contact sheet. Protection checks count changed common source-core pixels before and after the shared palette. Those checks establish exact core retention, not unchanged contrast around every stroke.

**share_auto_test.zip** excludes large NPZ files and extra previews. Four full-resolution outputs, source, protection and settings are required. The color reference is added first if it fits, followed by automatic strength maps and raw denoiser views, within a 30-MiB budget. The JSON lists omitted optional files. If required images exceed the budget, individual files remain and no ZIP is produced. Source files are included so a subsequent test can use the actual input.

The **Legacy manual** toolbar button retains the earlier V2 comparison with automatic strength and broad correction disabled. Historical line/blotch comparison modules also force manual strengths to avoid mislabeling a reused backend candidate.

## Diagnostics

Save maps and Compare export exact arrays in `diagnostics_raw.npz` and pictures with a legend. Comparison prefixes are `manual_` and `auto_`.

- `auto_luminance_strength`, `auto_chroma_strength`: actual 0–1 fields applied to both surface candidates. These are permission weights, not noise probabilities.
- `auto_color_variation`: medium chroma variation divided by 2 for display. `auto_luminance_coherence`: directional coherence, 0–1.
- `source_line_core`: binary original-pixel protection passed to both cleanup stages. White pixels keep source RGB before final color correction. Reference geometry does not supply this map.
- `unprotected_denoise_signed_rgb`: raw backend minus original; `guard_signed_rgb`: guards/source copy-back minus raw backend. Their sum is `denoise_signed_rgb`. When Auto skips the backend, the raw denoising change is zero.
- `local_cleanup_signed_rgb`, `blotch_signed_rgb`: actual local/broad corrections after automatic limits. Their sum is `cleanup_signed_rgb`.
- `denoise_signed_rgb`, `cleanup_signed_rgb`, `palette_signed_rgb`: actual stages whose sum equals `total_signed_rgb`. Native signed values are int16 RGB, after minus before.
- `*_change`: mean absolute RGB change divided by 16, with the same fixed display scale for every stage. The legacy `difference` alias is total change divided by 70. Neither is a detected-noise map.
- `blotch_automatic_amount`: V2.4's candidate confidence before the additional V2.6 limits; consult `blotch_change` for applied correction. `v2_boundaries` and `blotch_boundaries` show actual cleanup exclusions.

Heatmap colors encode numbers, not the original hue or kind of noise. Signed previews show separate RGB channels, blue for negative, gray for zero and orange for positive, saturating at +/-16 levels; they can be resized. NPZ retains exact values. Raw map exports can use substantial disk space at 2K/4K.

## Retained processing

All structural analysis uses the edited image. Supported weak source edges link to strong seeds or survive as long coherent segments; a small support band retains stroke centers. BM3D/NLM do not accept these masks internally. Legacy blending and exact source-core copy-back happen at their handoff. V2 cleanup uses the same core inside its sampling barriers.

Local cleanup samples similar LAB neighbors at fine/medium/broad distances on the full-resolution grid. A straight sampling path must avoid blocked boundary links. Broad normalization partitions unprotected interiors, detrends regional samples, smooths local residuals, and fades correction beside boundaries. Its candidate steps remain capped at 3 LAB units and within the observed 49×49 RGB envelope. Auto only limits those candidates; cleanup algorithms and BM3D adapters are unchanged.

Reference correction uses the inherited global LAB color engine, last. It can recolor protected line pixels and compress faint contrast. It retains known palette bias/halo limitations. Preserve Edits remains the existing registered pixel-replacement workflow; it requires matching input dimensions and ignores the new restoration controller. Restore Quality allows differently sized references.

## Installation, themes and input

Extract outside Forge. Use 64-bit Python with Tkinter; Python 3.11/3.12 are recommended for optional BM3D dependencies. Start **START_Difference_Guard.bat**. Base requirements include `tkinterdnd2==0.7.0`, with native Tcl/Tk 9 support. The launcher upgrades an older installation. Internet is needed for initial dependencies; normal launches with dependencies present do not run pip.

Each extracted folder has its own `.venv`. Install optional CPU/GPU BM3D there using the app buttons. Updating an existing folder can reuse its installed environment; do not copy virtual environments between machines. CPU BM3D uses `bm3d==4.0.3`; GPU uses `bm3d-cupy[cuda12]==0.1.3`.

Drop one image onto either input panel or its Open button. Spaces, braces and Unicode paths are parsed as a Tcl file list. Multiple files are rejected. Inputs cannot change during processing; replacing one clears stale output. File dialogs remember each input's last directory. If native drag/drop fails, Open remains available and startup.log records the error. Launch normally for Windows Explorer drag/drop.

System/Dark/Light themes remain. Windows System follows AppsUseLightTheme; other systems default to dark if detection is unavailable. Native dialogs use the OS theme.

## Timings and hardware

Live elapsed and completed stage timings remain. Save PNG writes the actual run settings, effective automatic choices and timings alongside the image, even if controls changed afterward. Timers exclude input loading, rendering and export. Automatic estimation is included in source-analysis time. First GPU execution can include CUDA setup/compilation. Local/broad cleanup runs on CPU NumPy/OpenCV.

GPU BM3D errors are explicit; no CPU fallback runs. Auto can legitimately skip GPU work when it detects no need for fine denoising, which is recorded separately. A CuPy CUDA-path warning alone is not a traceback or proof of an incomplete install. If a GPU stage finishes it executed and synchronized GPU operations. This Linux development environment has no GPU to validate that path.

Optional backend license references: [CPU BM3D](https://pypi.org/project/bm3d/) (published noncommercial package terms), [bm3d-cupy](https://pypi.org/project/bm3d-cupy/) and its [source](https://github.com/kvttt/bm3d_cupy).

## Developer checks

Install base requirements, CPU BM3D and pytest, then run `python -m pytest -q`. Native Tk integration tests need a display on Linux. See [VALIDATION.md](VALIDATION.md) for actual checks and the smoke diagnosis. Dependencies and virtual environments are not committed.
