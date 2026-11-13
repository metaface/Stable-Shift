# Stable Shift

Standalone experiments for correcting color drift and cleaning Stable Diffusion outputs while retaining the edited image's structure. Forge Neo integration and AI-assisted restoration are later work.

## V2.0 — Surface Cleanup Lab

1. Choose **Code → Download ZIP** above, then extract it. Keep your V1.1 folder for comparison.
2. Run **START_Difference_Guard.bat**. It installs/upgrades the drag-and-drop dependency in this app's `.venv` if needed.
3. **Drag one image onto COLOR REFERENCE and one onto EDITED.** The Open buttons still work and remember each input's last folder.
4. Select **GPU BM3D** if installed. Use its install button if this is a fresh folder.
5. Start with **Surface cleanup 60**, **Brightness cleanup 60**, **Color similarity 12**, **Radius 16**, then choose **Compare V2**.

Comparison exports the selected denoiser alone, denoiser + V2 cleanup, and V2 cleanup alone, all with the same color correction. It includes full-resolution PNGs, matching native-resolution crops, boundary/change maps, actual settings, and per-stage timings.

**The first image supplies color information only.** All denoising and structure/cleanup analysis use the second image or its denoised result. Different reference sizes remain supported in Restore Quality.

V2 replaces the faint V1.1 chroma-only finishing stage with full-resolution, color-and-boundary-constrained neighborhood estimates at fine, medium, and broad scales. It can also clean brightness variation. **It is an experimental local estimator, not a trained model or semantic segmentation.** Detected boundaries constrain sampling during the operation; undetected details can still be smoothed.

See [STANDALONE.md](STANDALONE.md) for controls, installation, limitations and timing details, and [VALIDATION.md](VALIDATION.md) for checks performed. Windows Explorer drag/drop still needs your local verification. GPU BM3D is the same adapter as V1.1, which you reported ran over 5× faster with comparable appearance; no new GPU speedup is claimed here.
