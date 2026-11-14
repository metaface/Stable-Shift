# Stable Shift

Standalone image cleanup and color restoration for Stable Diffusion outputs.

## V2.7 — multiscale automatic strength

V2.7 corrects the V2.6 controller's weak response to correlated blotches and grid texture. It measures scatter at the native size and several coarser analysis scales. The original full-resolution pixels still supply every denoiser and cleanup stage. Strong candidates are limited by location, including at the denoiser handoff, so noisy colored surfaces can receive more cleanup while quieter gray detail receives less.

1. Download this branch's ZIP, extract separately and run **START_Difference_Guard.bat**.
2. Load/drop the edited image and color reference. Leave **Automatic strength** and source-line tracing on. Strength sliders start at 100 as ceilings; retain your usual similarity range and radius.
3. **Run / Preview** produces the automatic result. Turn Automatic strength off for direct manual control.
4. For a controlled test, choose **Compare auto**. Compare **02_manual_same_palette.png** with **03_auto_same_palette.png** at native resolution. Both get exactly the same color correction field. The 00/01 pair isolates processing before colors.
5. Feedback can use **share_auto_test.zip**. It includes full-size outputs, source, protection and settings. The reference, raw/controlled denoiser views and selected maps are added within a 30-MiB budget. Large NPZ maps stay outside it.

V2.6 could skip BM3D when native grain was small even though broader contamination remained. V2.7 can select a stronger candidate from eligible multiscale variation, then limit its actual effect in luminance and chroma. Candidate strength is not the strength applied everywhere. Automatic detection remains heuristic: gray-only broad blotches and some texture can remain, while intentional colored texture can be softened.

The reference supplies colors only. V2.4's source tracer, local/broad cleanup and color-estimation algorithms remain the manual baseline. V2.5 faint continuation stays optional in API/legacy tests. Compare auto may run the backend twice; normal Run fits its own palette, while the comparison freezes the manual field.

Themes, drag/drop, timings, CPU/GPU BM3D and Preserve Edits remain available. See [STANDALONE.md](STANDALONE.md) for operation and [VALIDATION.md](VALIDATION.md) for measured checks and limits.
