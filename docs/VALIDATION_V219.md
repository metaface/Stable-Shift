# V2.19 — stop border sampling before it creates dark paint spots

The user's repeated nose crop still showed dark speckles after V2.18. That
version restricted stroke fitting and source copy-back, but the same spots
were already present in its zero-strength base. Preserving the nose's pigment
pixels was not a test of whether adjacent speckles disappeared.

## Located cause and change

Replay of native, coarse-paint, pyramid, wide-copy, border-cleanup and fitted
stages locates the severe spots at `clean_line_borders`. The original sampler
only stopped at recognized two-sided ink profiles. A broad filled object can
have a one-sided boundary, so a ray could pass into its dark edge. The selected
coarse sample could also fall into blurred ink just before that boundary.
The last valid sample unconditionally won. Negative coverage was clipped to
zero and the wrong dark paint was used as a replacement.

The sampler now tracks source luminance while moving outward from ink. A drop
of more than 12 RGB luminance levels from the highest encountered value stops
that ray permanently. Recognized ink still blocks it. Replacement paint comes
from the brightest valid coarse sample, with the existing gentle, consistent
trend extrapolation retained. This prevents a distant dark blurred edge from
overriding clearer paint earlier on the same ray.

This changes preparation for the live pyramid and the line-border comparison,
including the live zero endpoint. It adds no post-fit filter, median replacement,
slider or dependency. V2.18's connected-path fitting, source gating, common
color fit and cached preview blending retain their algorithms. Normal Run and
the other comparison paths retain their processing.

`00_original_preservation_base.png` now contains the current corrected border
base before trace gating. It is not a frozen V2.14/V2.18 control. Exact earlier
outputs are kept separately for validation.

## Validation

New regression fixtures place a clean paint gap between a colored stroke and a
broad filled object, including reversed geometry and two palettes. The previous
sampler invented a dark band there. The corrected result keeps the clean gap
within one RGB level and leaves the checked opaque stroke/object pixels exact.
Gentle shading is checked in both directions, alongside the existing fringe,
antialiasing, curved-stroke, small-gap and line-fitting tests.

Full-size replay uses the verified native/half/quarter CPU layers for the user's
cabin, beach and alley pairs, through actual live preparation. V2.18 outputs
are independent saved controls. It checks the previously reported paint spots,
the filled nose region at all preview strengths, changes outside fitted support,
and the shared-color metadata. The alley's original warm reference is not
available, so its correction stays off. Native Windows/GPU execution is not
available here.

The Linux/Xvfb suite passes **201 tests**, with one historical image test
skipped for its missing fixture. All three cached-layer full-size replays pass;
their requested options and complete color-correction reports match V2.18.
The engine, pyramid and connected-path fitting code retain their algorithms.

Two previously darkened cabin paint locations change as follows in the actual
zero-strength output, with the same values retained at 200 percent:

| Native location (x, y) | V2.18 RGB | V2.19 RGB |
| --- | --- | --- |
| (691, 530), beside the nose | (83, 87, 86) | (122, 128, 131) |
| (716, 562), below the nose | (72, 79, 78) | (130, 137, 137) |

A fixed 1,102-pixel gray-paint sample around that nose is also checked against
the same native-color input. Additional five-pixel dark-deficit responses above
eight levels decrease from 185 pixels to 74; their summed additional deficit
decreases from 6,020.7 to 2,280.0. This is an artifact diagnostic on this crop,
not a claim that a percentage of all image noise is removed. The remaining
responses are not all eliminated.

The earlier 1,856-pixel thresholded nose region remains identical between the
new 0/25/50/100/200-percent views. It is **not** identical between versions:
144 of those pixels change during the corrected border preparation, including
highlights that the old sampler had darkened. Fitting does not add changes in
that region. These checks do not establish semantic shape preservation for
every image; the separate known-object fixtures retain exact opaque pixels.

This is a source-based sampling correction, not semantic restoration. Gradual
or nearly equal-luminance boundaries can evade the new stop rule; unusually
strong remaining source noise can stop a valid ray. Old source texture and
long structured noise remain possible. The result still needs visual testing
on the user's actual backend and settings.
