# Stable Shift

Standalone cleanup/color-restoration experiments for Stable Diffusion outputs.

## V2.5 — faint-line continuity

The current test targets faint or interrupted strokes. It retains V2.4's accepted blotch cleanup and color-estimation algorithms.

1. Download this branch's ZIP and extract it separately. Run **START_Difference_Guard.bat**.
2. Load/drop the usual edited image and color reference. Keep the cleanup/denoiser settings you liked, including broad correction 100 if that was your preferred result.
3. Leave **Trace source lines** enabled and choose **Compare lines**.
4. Compare **02_v24_same_palette.png** with **03_faint_lines_same_palette.png** at native resolution. The 00/01 pair isolates processing before color correction.
5. To send the test back, upload **share_line_test.zip** from the comparison folder. It contains full-size outputs, the original edited RGB, line masks and settings; large NPZ maps stay outside it. A share ZIP is created when those files fit below 30 MiB.

The updated tracer retains weaker source edge pixels between matching traced segments, using short tangent corridors and matching gradient polarity. It adds protection only where the previous protection band had a hole. Existing protected pixels are retained, and added pixels cannot seed further growth. Blank gaps are not redrawn.

**The comparison runs the denoiser once.** Both variants use the same candidate, cleanup settings and frozen V2.4 baseline palette field. The only switched feature is faint-segment continuation. Reports count added protection and verify that the previous core stays unchanged. Run/Preview uses the updated tracing by default; its palette is fitted normally from that run's local-cleanup result.

This is targeted protection, not line enhancement or reconstruction. A stroke absent from the edited source, a long unsupported gap, or contrast compressed by palette conversion can still remain faint. Some noise inside protected bands remains too.

Drag/drop, system/dark/light themes, CPU/GPU BM3D and Preserve Edits are retained. No antialiasing, generative restoration or lighting controls are added. See [VALIDATION.md](VALIDATION.md) for measured checks and limits, and [STANDALONE.md](STANDALONE.md) for installation and diagnostics.
