# V2.21 — focused color cleanup after SCUNet

The new standalone path keeps SCUNet as the denoiser and tests one extra
color-averaging pass. It does not reuse the old sequence of guarded denoising,
local/broad cleanup, coarse reconstruction and line fitting.

## Processing and controls

The official pinned real-PSNR checkpoint and V2.20 inference implementation
are unchanged. Native RGB model output supplies every cleanup sample. OpenCV's
recursive domain-transform filter (`edgePreservingFilter`, flags 1) averages
similar neighboring colors, including brightness. Regular uses spatial sigma
100 native pixels and color range 0.05. Strong uses 120 and 0.10. Both start
independently from the model result, without binary protection or region fills.

One robust uniform RGB correction is fitted to SCUNet alone and applied to
the model-only, regular and strong endpoints. Reference correction can be
disabled; an unreliable fit also leaves source colors. No spatial Classic
correction or reference geometry participates. The coefficients can differ
from V2.20's comparison, whose fit comes from the classical comparator.

The live 0–200 control blends immutable endpoints rather than rerunning any
analysis. Zero is exactly the model output passed through the frozen transform.
Repeated rendering is reversible and non-cumulative. Preparation can reuse a
raw model cache only when edited-image pixel signatures match. Color fitting
and cleanup are recomputed on a new preparation. Saved images, tests and maps
use the displayed cache and applied strength, even with a pending widget edit.
Workers carry generation IDs so stale success/failure messages cannot replace
newer results or clear another operation's busy state.

Ordinary Run and the V2.20 SCUNet comparison retain their processing. A cached
SCUNet-cleanup preview is explicitly excluded from reuse as the classical
comparison control. Setup/dependencies and the default backend are unchanged.

## Checks

Synthetic drawings test substantial broad lightness/color-patch reduction at
the regular setting, hard shading contrast, colored line position/width,
stitch gaps, filled-feature silhouettes, bright smoke without a new dark
outline, smooth gradient direction/span, tiny/constant inputs and invalid RGB.
Cache/export checks verify exact zero, common frozen coefficients, reversible
blends, unchanged source pixels, rejection of stale input exports and no call
into the classical reconstruction stack. Real Tk tests cover preparation,
cached slider updates, displayed-strength saves, failure/stale-worker handling
and switching back to the older live line test.

The new cleanup is replayed on the three cached 2048x2048 outputs from actual
V2.20 SCUNet CPU inference: cabin, beach and alley. This reuses real network
pixels, not synthetic denoiser substitutes, and avoids repeating an unchanged
model run for every filter adjustment. All strengths share one fresh frozen
global fit per case. Zero is checked exactly against that fit applied to the
raw model output. Endpoint PNGs, original inputs, native crops, actual settings
and share archives remain available for visual review.

On a fixed interior thigh crop, broad patch RMS (Gaussian scales 6 minus 32,
RGB levels) falls from 0.779 at zero to 0.351 at 100 and 0.279 at 200. This
describes variation in that crop, not a perceptual quality score. Visual checks
include the nose, tree shading, iridescent markings, beach sparkles and smoke.
The simple pass avoids the isolated spots and contour bands observed in the
discarded region-fill prototype. It can still reduce legitimate faint details,
gradients and texture, especially at 200; edge awareness is not semantic
understanding. Exact preservation of every SCUNet line pixel is not claimed.

These full-size cleanup endpoints each took roughly one second on the shared
CPU; that excludes inference, color fitting and export. The small standalone
ZIP includes source/docs, not PyTorch, model weights or test images. Windows
and CUDA execution are unavailable here; the user's GPU speed observation is
not treated as a locally measured benchmark.

A fresh 384x256 cabin crop also ran end to end through the new preparation
using the verified real checkpoint, CPU float32, PyTorch 2.15.0+cpu and Spandrel
0.4.2. Model inference took 15.43 seconds on the shared two-thread CPU; exact
zero and reversible cached cleanup were checked. The three full-size share
bundles are 21,007,714, 29,484,495 and 20,424,558 bytes for cabin, beach and alley.
The beach ZIP omits raw model output to fit; that output remains in its full
folder. Compared controls, selected results and original inputs are retained.

The final Linux/Xvfb suite passes **267 tests**, with one unavailable historical
real-image fixture skipped. The standalone archive contains 50 runtime/doc
files and builds byte-identically twice. The new live row was also inspected
with a real cached output at 1400x980 and the minimum 1040x820 window size.
