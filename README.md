# Stable Shift

Standalone cleanup/color-restoration experiments for Stable Diffusion outputs.

## V2.4 — local blotch correction

This test revises the extra blotch pass that caused outlines, eye patches and lost shading in V2.3. It includes the accepted V2.1 line tracing and palette behavior. Download this branch directly; merging the earlier experimental branches is unnecessary.

1. Download this branch's ZIP and extract it. Keep your working V2.1 folder separately.
2. Run **START_Difference_Guard.bat** and load/drop the same reference and edited image.
3. Use the same denoiser and existing cleanup settings as your previous comparison. Leave source-line tracing enabled.
4. Start **Broad correction maximum** at **70** and select **Compare blotches**. You can repeat at **100** to check the previous failure cases.
5. Compare **02_v21_same_palette.png** with **03_broad_same_palette.png** at native resolution. The **00/01** pair isolates cleanup before color correction.

The new pass smooths local residual patches while retaining broader shading. It fades its correction beside protected edges, rejects heterogeneous neighborhoods even at a permissive similarity setting, limits each color move, and prevents output channels from exceeding the observed local source range. Cleanup is deliberately more restrained than V2.3's regional surface replacement.

**BM3D runs once per comparison.** Both outputs receive one frozen V2.1 palette field fitted from the shared baseline. The source tracer, existing local cleanup and color estimator are held fixed. Reports now include changes immediately beside protected lines as well as exact changes on the lines themselves; unchanged line pixels alone do not prove that a line remains visible.

Development checks used the supplied full-resolution comparison, a cached full-resolution beach baseline with its actual source mask, and controlled blotch/shading tests. The supplied comparison lacks the original source mask, so that replay conservatively freezes every pixel V2.3 left unchanged. It is a cleanup-only replay, not a reproduction of the entire original run. See [VALIDATION.md](VALIDATION.md) for measured results and limits.

This still cannot reliably distinguish every intentional texture from a blotch. Some noise, protected fringes and sparkle halos will remain. Automatic estimation applies to the extra blotch pass; BM3D strengths are not automatically calibrated. No antialiasing, generative restoration, lighting progression or Forge integration is included.

Only the edited image supplies structure; the reference supplies colors. Drag/drop, system/dark/light themes and CPU/GPU BM3D remain available. See [STANDALONE.md](STANDALONE.md) for installation, controls and diagnostics.
