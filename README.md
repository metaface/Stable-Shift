# Stable Shift

Standalone experiments for correcting color drift and cleaning Stable Diffusion outputs while retaining the edited image's structure. Forge Neo integration and AI-assisted restoration are later work.

## V2.1 — carry source-line protection through cleanup

1. Choose **Code → Download ZIP**, extract separately, and run **START_Difference_Guard.bat**.
2. Drop your color reference and edited image into their input panels.
3. Select **GPU BM3D** and leave **Trace source lines before denoising and protect them through cleanup** checked.
4. Start with Surface cleanup **60**, Brightness cleanup **60**, Color similarity **12**, Radius **16**.
5. Click **Compare V2**. First compare `01_denoiser_only.png` against `02_denoiser_source_lines.png` to judge line preservation without surface cleanup. Then compare `03_denoiser_plus_surface.png` to judge cleanup.

With a denoiser selected and source tracing enabled, comparison exports four variants:

- V2 baseline: existing denoiser and legacy guards, no source tracing or surface cleanup.
- Same denoiser + linked source-line protection, no surface cleanup.
- Same denoiser + source-line protection + surface cleanup.
- Source-protected surface cleanup alone.

**New in V2.1:** hard and soft structure are linked from the original edited image, before denoising. The same source mask preserves line pixels at the denoiser handoff and blocks cleanup sampling through those pixels. A line no longer has to survive denoising to be detected by cleanup.

**BM3D itself is unchanged.** It does not accept our custom boundary mask internally; its source-line preservation is applied at the handoff. The V2 cleanup does enforce the carried mask inside its sampling operation. Undetected details can still soften, and noise on protected lines can remain.

Map exports now distinguish denoising, cleanup, palette-only and total changes. They include exact signed RGB arrays, black/white protection maps and a `MAP_LEGEND`. The total difference image is **not** a detected-noise map.

The first image supplies color information only. All structure comes from the second image. Different reference sizes, drag/drop, system/dark/light themes and per-stage timings remain supported.

See [STANDALONE.md](STANDALONE.md) for controls and map meanings, and [VALIDATION.md](VALIDATION.md) for checks and limitations. Keep V2.0/V1.1 separately for comparison.
