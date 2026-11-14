# Stable Shift

Standalone image cleanup and color restoration for Stable Diffusion outputs.

## V2.8 — bright surface cleanup

V2.8 targets the gray/blue mottling left around sparkles on bright fur. The selected denoiser settings stay the same as V2.7. Auto gives the existing correction more permission within bright, near-neutral surfaces that contain fine texture, while retaining the exact source-line mask. The additional cue is zero on the supplied alley and cabin inputs, leaving their processing unchanged.

1. Download this branch's ZIP, extract separately and run **START_Difference_Guard.bat**.
2. Load/drop the edited image and color reference. Leave **Automatic strength** and source-line tracing on. Retain your usual settings; sliders remain ceilings.
3. **Run / Preview** produces the automatic result. Turn Automatic strength off for direct manual control.
4. For a controlled test, use **Compare auto**. Compare **02_manual_same_palette.png** with **03_auto_same_palette.png**. Both receive the same color correction field; 00/01 isolate processing before colors.
5. **share_auto_test.zip** contains full-size outputs, source, protection and settings. The reference and selected diagnostics are added within a 30-MiB budget; large NPZ maps stay outside it.

The reference supplies colors only. V2.7's multiscale candidate estimator and the accepted V2.4 source tracer, local/broad cleanup, palette matcher and manual behavior are retained. The new rule changes where existing candidates are applied; it adds no restoration filter or model.

This remains heuristic. It can soften intentional fine gray texture on bright neutral objects, and some sparkle glow/mottling can remain. Themes, drag/drop, timings, CPU/GPU BM3D and Preserve Edits remain available. See [STANDALONE.md](STANDALONE.md) and [VALIDATION.md](VALIDATION.md) for details and actual checks.
