# V2.15 — cached live line preservation

The requested test varies dark-stroke preservation on the preferred V2.14
cleaned pyramid without repeating the upstream processing. Normal Run,
denoisers, color fitting, source tracing, pyramid reconstruction and border
cleanup implementations are unchanged. The new source-profile recovery and
live UI are isolated in `stable_shift/live_lines.py` and `stable_shift/app.py`.

Preparation runs the native, quarter and half paths once, retaining the exact
V2.14 base. Source-only two-sided darker profiles and short directional support
identify recovery locations within source line evidence. At 100, darker source
RGB is restored only at those locations. At 200, coverage can move toward
observed nearby ink along its normal. No fixed black or wide raw paint residual
is added. All three endpoints receive one frozen global RGB transform; final
luminance checks prevent color fitting from reversing the intended darkening.
An unavailable/rejected fit leaves every endpoint in source colors.

Slider rendering copies a fixed base and blends precomputed sparse RGB values.
It does not call the denoiser, line classifier, reconstruction or color fitter.
Updates are throttled while dragging, rather than postponed until dragging
stops. Native zoom crops before display scaling; zoom/pan never change saved
pixels. Saves use the applied strength, frozen options and displayed cache,
even if a new slider value is pending or a replacement cache is awaiting a
valid setting. Stale workers cannot overwrite newer results. Changing an input
or starting normal Run invalidates the live cache.

## Checks

Synthetic cases verify recovery of colored ink, preservation of a lighter paint
fringe, rejection of one-sided shade steps and isolated dots, observed-color
bounds, reversible/noncumulative slider rendering, immutable cached pixels,
invalid-strength rejection, exact native/zoom crop coordinates, full-size
exports, actual strength metadata and exact signed diagnostic arrays. Backend,
reconstruction and color-fit traps verify that slider rendering cannot call
those paths. A preparation spy checks all three independent scales and common
finishing-off settings. Native Tk tests exercise preparation, latest-value
rendering, stale-worker rejection, strength changes, input invalidation and
saving the displayed setting while another widget value is pending.

The supplied 2048-pixel cabin, beach and alley images were replayed using the
verified actual CPU BM3D candidates and independently executed coarse layers.
Original source pixels, native backend arguments, exact BOX reductions and all
coarse processing options are checked before reuse. The cabin and beach use
their supplied reference files; alley reference correction remains off because
the original warm reference file is unavailable here.

Every RGB pixel at **0% matches V2.14** in all three full-size cases. Native
crops show stronger ink at the upper end, including visible thickening at 200.
These changes are not noise-removal percentages or semantic preservation scores.

| Input | Pixels changed at 100% | Pixels changed at 200% |
| --- | ---: | ---: |
| Cabin | 0.343% | 3.231% |
| Beach | 0.422% | 3.645% |
| Alley | 0.386% | 3.461% |

Cached pixel blends on these images took approximately **6–17 ms** in this Linux
environment, excluding Tk redraw and preparation. This is not a guarantee of
Windows UI latency. Existing GPU adapters and dependencies are unchanged;
native Windows and GPU execution are unavailable here.

The line model does not reconstruct absent geometry, recognize stitching
semantically, recover all shading edges or remove noise already inside ink.
Large strengths can make strokes thicker or retain unwanted dark source marks.
The live range exists so these tradeoffs can be inspected without repeated
denoising. The accepted cleanup/color algorithms have not been retuned.

Final Linux suite with a real Tk display: **160 passed, 1 skipped**. The skip is
the historical real-image fixture unavailable in this environment. The
deterministic standalone build excludes tests, user images and validation
outputs; it includes the live-preview module and this guide.
