# V2.18 — connected paths authorize preservation and fitting

This records the V2.18 test. Subsequent user testing still showed the nose-area
speckles. Its unchanged-nose and path tests did not establish their removal.
Stage-by-stage replay found the earlier line-border sampler creating dark paint
spots; V2.19 corrects that stage. See [the follow-up validation](VALIDATION_V219.md).

The previous candidate accepted dark components containing five pixels and
used direction-compatible neighbors without proving they belonged to the same
stroke. A fragment in the wide source guard could therefore survive copy-back
or borrow nearby dark color. V2.17's final median cleanup did not address this
cause and was reported to alter the nose. That cleanup and its runtime module
are removed in V2.18.

## Processing change

The carried source guard limits the search area; it does not independently
authorize output ink. Actual native dark valleys must have lighter paint on
both sides. Their centerline is thinned and converted into a pixel-adjacency
graph. Redundant diagonal shortcuts are omitted. Short terminal branches are
pruned, while independent short marks remain available as unfitted details.
Chains split at junctions and require at least 12 native pixels of arc length
plus eight pixels of spatial extent. Pixel count alone is insufficient: a large
dirty grid with short branches is rejected.

Each accepted chain receives a distinct ID and arc-position field. Rejected
skeleton pixels keep ownership of their neighborhoods with ID zero, so a nearby
valid stroke cannot absorb them. Fitting color/geometry/width samples must match
the current path ID and remain nearby along that chain. Only genuinely closed
chains can wrap their arc distance; nearby ends of an open curve cannot borrow
samples across the gap. Native samples avoid
bilinear color mixing between IDs. RGB ink comes from observed samples on the
path. An untraced adjacent dark detail cannot supply ink or be repainted as a
line's antialiased margin. Final coverage uses 4x4 area sampling; per-path
integrated opacity constrains width changes. Regular and stronger tangent
smoothing use five- and eight-pixel sigmas within the accepted path.

Compact closed dark-filled details are recognized separately from thin strokes.
Their native pixels are kept, and fitting excludes both the filled interior and
its nearby observed rim. Junctions and endpoints have additional exclusions.
This does not globally freeze every large connected outline as a filled shape.

The same validation gates source preservation before fitting. Pixels in the old
wide source guard that have no justified copy-back return to the independently
reconstructed quarter/half/full pyramid. Short simple marks and recognized
filled details retain their source preservation. No median or replacement
patch is applied after fitting. The old wide-preservation result remains an
exported control. Global color coefficients and upstream cleanup are unchanged.

The live slider still uses fixed cached views: zero is traced preservation,
100 is regular fitting and 200 is longer same-path fitting. Its value does not
weaken path validation. Source-preservation and fitting signed maps add exactly
to the displayed correction from the exported original base.

## Checks

Independent fixtures cover a true long stroke, a connected dirty grid containing
over 100 pixels, tiny nearby fragments, isolated short dashes, two-pixel gaps,
faint lines next to heavy ink, separate colored parallel paths, crossing
junctions, short attached spurs, tiny closed loops and tiny images. A known
asymmetric filled nose, its highlight and a broader dark-rimmed filled detail
must retain their exact foreground RGB. The known jagged colored stroke still
requires substantially reduced center jitter and bounded equivalent width.

An integration test verifies that the trace gates actual source copy-back and
is reused by fitting rather than rebuilt on slider changes. Original-base
export, exact signed-map sums, native zoom/pan, stale workers and applied-setting
metadata remain covered.

Full-size replay uses verified native/coarse CPU layers for the supplied cabin,
beach and alley inputs. Source pixels/options match before reuse. Pyramid,
border cleanup, tracing, copy-back gating, fitting and shared color fitting run
through the actual preparation function. The original exported control must
match V2.14 at every RGB pixel. All recognized filled-region pixels must match
that control at every strength, and fitting cannot change pixels outside its
validated support. The cabin nose is also checked independently using its
connected dark pigment region, including the rim that the first exclusion
missed. The original warm alley reference is unavailable, so its correction
remains off.

The Linux/Xvfb suite passes **196 tests**, with one historical real-image test
skipped because its fixture is unavailable. The separate three-input replay
above passes. It validates 2,503 cabin, 3,793 beach and 3,295 alley paths, all
at least 12 pixels long. The cabin's independently selected 1,856-pixel nose
pigment region, including its rim, is byte-identical to the original control
at 0, 25, 50, 100 and 200 percent. These counts describe checks, not a semantic
quality score.

On the known jagged colored-stroke fixture, center jitter drops from 0.822 pixels
to 0.449 at 100 percent and 0.433 at 200 percent. Equivalent ink width changes
from 2.943 to 3.000 and 2.982 pixels respectively. This verifies actual smoothing
without the previous widening approach; inherited grain can still remain.

This remains geometric restoration, not semantic recognition. Long structured
texture can resemble a real stroke; genuinely missing or unusually tangled
strokes can fail validation. Tiny complex details can stay on the pyramid.
Unrecognized filled objects and existing texture remain limits. Native Windows
and GPU execution are unavailable here; their adapters are unchanged.
