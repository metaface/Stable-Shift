# Stable Shift

Standalone image cleanup and color restoration for Stable Diffusion outputs.

## V2.6 — automatic strength test

Automatic strength measures fine scatter separately from broader colored variation, then limits the existing cleanup around coherent structure. It uses the edited image only. The reference still supplies colors only.

1. Download this branch's ZIP, extract separately and run **START_Difference_Guard.bat**.
2. Load/drop the edited image and color reference. Leave **Automatic strength** and source-line tracing on. The strength sliders start at 100 as ceilings; retain your usual similarity range and radius.
3. **Run / Preview** produces the automatic result. Turn Automatic strength off to use the sliders directly.
4. For a controlled test, choose **Compare auto**. Compare **02_manual_same_palette.png** with **03_auto_same_palette.png** at native resolution. Both get exactly the same color correction field. The 00/01 pair shows processing before colors.
5. Feedback can use **share_auto_test.zip** from the timestamped comparison folder. It includes full-size outputs, source, protection and settings; the reference and selected diagnostic images are included within a 30-MiB budget. Large NPZ maps stay outside it.

Automatic strength can skip fine denoising when measured scatter is below the backend's minimum. Additional brightness cleanup requires colored variation, so smoke and uncertain gray texture receive less processing. This deliberately leaves more ambiguous texture than maximum manual settings. It is a conservative heuristic, not semantic recognition of noise or artistic intent.

V2.4's cleanup and color-estimation algorithms are retained. Its source tracer is the default again; the V2.5 faint-segment extension remains available to API/legacy tests. **Compare auto may run the backend twice**, because its two strengths differ. Normal Run fits its own palette; the controlled comparison freezes the manual field.

System/dark/light themes, drag/drop, timings, CPU/GPU BM3D and Preserve Edits remain available. See [STANDALONE.md](STANDALONE.md) for controls and diagnostics, and [VALIDATION.md](VALIDATION.md) for measured checks and limits.
