# V2.17 — withdrawn surface-fragment experiment

This candidate was withdrawn after the user reported persistent speckling and changes to the nose shape. V2.18 removes this cleanup and validates connected source paths instead. The checks below describe the historical experiment, not the active method.

The reported speckling is present in saved PNGs at zero strength. On the cached
supplied cabin pair it is also visible in the retained older zero-strength
base. Thus the slider alone cannot remove it. Earlier whole-image equality
checks established that the base was unchanged; they did not establish that
the base was free of these small paint artifacts.

V2.17 retains the V2.16 fitting implementation byte for byte. Native/coarse
cleanup, border reconstruction and shared color fitting are unchanged. A small
final surface-fragment cleanup processes each cached zero/regular/strong RGB
view once, before it becomes available to the live slider. No backend, fitting
or cleanup is repeated on slider movement.

The cleanup compares pixels with a local paint median, then separates compact
negative outliers from established ink. Its ink exclusion uses relative local
contrast and connected support. Including the full neighborhood color range
prevents gray speckles next to a broad black nose from declaring themselves the
darkest available ink. A separate source-evidence/distance limit confines the
repair to nearby paint. Small remote dots cannot act as their own established
ink anchors. Thin elongated marks, filled short dashes and larger connected
components are excluded. Selected fragments have at most 48 pixels and a
10-pixel span. Only those pixels change, and their final RGB luminance increases.

This repair intentionally also changes the zero-strength view: zero now means
stroke reconstruction off, with surface-speckle cleanup retained. Exporting the
uncorrected base separately makes that change reviewable. The slider range,
default 100, native zoom/pan, actual-setting reports and stale-cache protections
remain. All prior color/denoiser settings remain frozen during live previews.

## Checks

Synthetic tests cover gray and fully dark pepper next to ink, exact connected
line preservation, faint connectors, one/two-pixel short stitches, distant dark
details, bright sparkles, clean curves, shading interiors, empty support and
tiny/invalid inputs. Tests require unchanged pixels outside the repair mask,
actual lightening on repaired pixels and unmodified input arrays.

An integration fixture checks all three endpoint repairs after the one frozen
RGB transform, including cleanup at reconstruction zero. A call counter proves
that rendering strengths does not repeat cleanup. The dirty baseline and new
cleaned zero are exported independently. Exact signed arrays must sum to the
displayed correction from the original base. Existing fitting geometry,
stitch-gap, cached rendering, actual-settings and native Tk checks remain.

Full-size checks replay the verified V2.16 colored endpoints for the supplied
cabin, beach and alley inputs. Because the fitter, upstream stages and color
transform are unchanged, these isolate the new cleanup without repeating a
backend run. Each old zero must match the exported original base exactly;
each new endpoint may differ only in its own cleanup mask. The original warm
alley reference remains unavailable, so alley reference correction is off.

These checks passed for all three full-size pairs. Every repaired pixel became
lighter in final RGB luminance, and every pixel outside its repair mask stayed
identical. The original base export matches the saved V2.16 zero view exactly.
The cabin face crop has 3,408 repaired pixels at zero strength; this is a changed
pixel count, not a count of semantic defects or a percentage of noise removed.
Native face/nose/eyelid and other test crops were inspected. Connected boundary
grain remains visible in some places.

| Input | Pixels repaired at 0% | Pixels repaired at 100% | Pixels repaired at 200% |
| --- | ---: | ---: | ---: |
| Cabin | 29,009 | 31,104 | 31,433 |
| Beach | 44,875 | 49,743 | 50,447 |
| Alley | 23,758 | 22,144 | 23,683 |

Each endpoint's new cleanup took roughly 0.4–0.6 seconds in this Linux replay.
It runs during preparation, not slider rendering. The full suite under a real
Tk display passed **186 tests, with 1 skipped** for the unavailable historical
real-image fixture. The deterministic standalone archive contains 43 runtime
and documentation files; tests and user images are excluded.

The method does not semantically identify freckles, texture or punctuation.
Tiny ambiguous marks can be changed, and grain connected to real ink may
remain. It is a local cleanup, not a guarantee that every noisy border or
inherited source-grid artifact disappears. Native Windows/GPU execution is
unavailable here; adapters and dependencies are unchanged.
