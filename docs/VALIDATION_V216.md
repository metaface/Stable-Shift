# V2.16 — smooth fitted strokes in the live preview

V2.15 could only darken existing source pixels below 100%, which made that
range nearly inactive. Its upper range borrowed nearby darker pixels and
widened rough strokes. V2.16 replaces that candidate with fitted geometry and
signed coverage changes. The zero-strength pyramid, border cleanup, color fit,
denoisers and normal Run are unchanged.

Thin dark valleys inside the carried source evidence locate possible strokes
on the cleaned native base. A local under-ink paint estimate and observed ink
color provide an opacity model. The paint field itself is never used as a broad
replacement image. Normal profiles measure center positions and integrated
widths; only the nearest connected section is integrated so parallel lines do
not become one wide stroke. Compatible sections along the tangent regularize
those measurements. A 4x4 subpixel strip model rebuilds coverage. Corrections
can lighten an old protrusion or darken its replacement. The width is measured,
rather than expanded with strength. Ink-color cleanup removes modeled color
scatter without returning raw source paint.

At 100%, tangent fitting uses a 4-pixel Gaussian sigma; 200% uses 7 pixels.
Both candidates are built once, share one fixed color transform and are cached.
The slider interpolates base to regular to stronger fitting, with no new
backend/analysis work. The old darkening-only gate has been removed.

## Validation

A colored three-pixel stroke with known random position jitter and colored grid
cuts checks actual geometric improvement. Both powers must reduce center jitter
by at least 45%, retain average equivalent width within -15%/+10%, make both
lighter and darker corrections, and stay within the observed ink-color bound.
This would reject V2.15's widening-only candidate.

Fixtures also check separate parallel seams, one/two/three-pixel strokes with
two/three-pixel stitch gaps, ordinary shade/smoke steps, isolated dots, visible
changes at 25%, reversible/noncumulative rendering, invalid settings, signed
diagnostics and exports. Backend/color/reconstruction traps ensure slider
changes never rerun preparation. Existing Tk cache, stale-worker, zoom and save
metadata checks remain.

Full-size cabin, beach and alley checks use the verified V2.14 pre-color bases
and source cores, with their unchanged shared RGB transforms. Verified native
CPU BM3D candidates and independently executed quarter/half layers are reused
only after source pixels, backend arguments, exact reductions and coarse
options match. The original warm alley reference is unavailable, so alley
reference correction remains off. Every 0% RGB pixel must match V2.14.

All three full-size zero-strength controls matched V2.14 at every RGB pixel.
Final-stage replay used the verified pre-color base/core and the identical
stored RGB coefficients, then saved native crops at 0/25/50/100/200. The cabin
pocket/waist crop shows smoother ink instead of V2.15's broad dark growth; the
alley smoke crop retains its existing boundary while pavement strokes become
more regular. These are visual checks, not semantic preservation scores.

The known jagged-stroke fixture measured:

| View | Equivalent width | Center-position jitter (standard deviation) |
| --- | ---: | ---: |
| Input | 2.943 px | 0.822 px |
| 100% | 2.894 px | 0.311 px |
| 200% | 2.909 px | 0.256 px |

The full-size line-fit stage took about 5.6–5.9 seconds once, after the cached
upstream stages. Subsequent RGB blends took about 17–30 ms, excluding display.
These timings describe the Linux validation environment, not Windows latency.

Full suite with a real Tk display: **170 passed, 1 skipped**, the latter being
the unavailable historical real-image fixture. The deterministic standalone
package contains 41 runtime/documentation files and excludes tests and user
images. Existing UI/cache/zoom/export behavior remains covered.

This is local profile regularization, not semantic recognition or vector
reconstruction of absent lines. Tight intersections, sharp corners, low
contrast details and already-missing geometry can remain imperfect. Longer
fitting can round small details. Synthetic width bounds are not a guarantee
that every line in an arbitrary image keeps its exact width. Native Windows
and GPU execution are unavailable here; their adapters remain unchanged.
