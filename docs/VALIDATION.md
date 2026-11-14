# V2.8 processing validation

These are the accepted processing checks from before the file reorganization. Layout, packaging and migration checks are documented in [CLEANUP.md](CLEANUP.md).

## Issue and narrow change

The supplied beach comparison shows remaining gray/blue speckling around sparkle details in Auto, while maximum manual processing is preferred. V2.7 already selected luminance 100 and chroma 28.68577, so this was not another skipped-backend case. On free pixels in three sparkle crops, median luminance permission was only about 3–5%. The colored-variation requirement and extra automatic fade suppressed much of the available brightness correction.

V2.8 adds extra local permission for fine texture within a broadly supported bright, low-chroma surface. Source lightness/chroma, neighborhood support and fine-scale luminance scatter produce a bounded 0–1 cue. It raises the existing luminance/chroma permission fields for the backend handoff and both surface stages. It does not alter backend settings, source cores, palette matching or a restoration filter. Exact source cores and the retained filters' barriers still apply.

## Retained behavior

V2.7's candidate estimator is evaluated before the new cue. Its fine/multiscale estimates and selected denoiser values remain unchanged. The same exact source-line mask is used. Local and broad cleanup, palette/core modules, input loader, requirements and source tracing files remain byte-identical to V2.7. CPU/GPU BM3D implementations and manual behavior are retained.

On both supplied alley and cabin sources, the new cue is exactly zero. All existing automatic fields and effective options matched V2.7. Full-resolution cached-candidate replays also matched the previous actual CPU outputs byte-for-byte, including the cabin's final color correction: zero changed pixels in each image. This is stronger than checking an average permission value; these accepted examples follow the same processing path.

## Full-resolution beach comparison

The original source matches the earlier 2048×2048 beach source byte-for-byte. An actual CPU BM3D candidate was computed at the selected V2.7 settings, L=100 and C=28.6857693. That exact candidate was held fixed for old/new stage replays. Each replay verified the original RGB and exact backend arguments before accepting the cached candidate. Disabling only the new cue reproduced the original actual V2.7 CPU output byte-for-byte.

Both old and new results then received the same exact frozen palette field fitted to the retained maximum-manual CPU local baseline using the supplied reference. No reference geometry guides the new cue. Native crops of upper-body sparkles, torso, thigh, face and crystal details were inspected. V2.8 visibly clears much more of the mottled texture and approaches the preferred manual appearance, while some soft glow/texture remains.

| Full-resolution check | Result |
| --- | --- |
| Selected backend strengths changed | No |
| Extra cue active on beach | 491,126 pixels, 11.71% |
| Mean extra beach permission | 9.22% |
| Original protected RGB pixels changed before palette | 0 |
| Common protected RGB changes after the shared palette | 0 |
| Actual processing residuals sum exactly to output change | Yes |
| Alley final RGB changed in replay | 0 pixels |
| Cabin final RGB changed in replay | 0 pixels |

The active area and mean permission are weights/coverage, not percentages of noise removed. Candidate reuse isolates the permission change; replay timings are not backend performance benchmarks. GPU execution remains unverified here.

## Closeness to the supplied manual example

The following measurements exclude source-core pixels and compare native pre-palette RGB with the supplied maximum-manual GPU result. The old/new automatic replay uses the same actual CPU candidate. This is distance to the user's preferred example, not a ground-truth noise score or a CPU/GPU equivalence claim.

| Sparkle crop | V2.7 mean absolute RGB gap | V2.8 gap | Remaining gap / V2.7 |
| --- | ---: | ---: | ---: |
| Upper body, x690–1049 y620–849 | 2.259 | 0.500 | 0.221 |
| Torso, x830–1139 y830–1039 | 1.858 | 0.660 | 0.355 |
| Thigh, x520–849 y1000–1249 | 2.146 | 0.570 | 0.266 |

The substantially smaller gaps agree with the visible cleanup. They do not establish perfect sparkle preservation or semantic recognition of halos. Exact protected-pixel retention does not by itself prove unchanged contrast in every untraced detail.

## Automated checks

**80 tests passed, 1 skipped** under a real Linux Tk display. The skip is an unavailable historical image fixture. Existing tests include actual CPU BM3D, the native Compare auto button, drag/drop slots, themes, run-setting persistence, fine/correlated-noise reduction and signed stage accounting.

New checks cover:

- Extra permission for bright neutral fine texture, with exact exclusion of protected pixels.
- Zero extra permission for dark neutral and bright saturated controls.
- Unchanged backend strengths and honoring zero cleanup stages even when the cue is active.
- More than 50% MSE reduction against a known clean bright-gray surface using retained surface cleanup alone.
- A clean bright gradient remaining byte-identical over three automatic passes.

The accepted V2.4 manual regression also matched output RGB and source mask byte-for-byte. No dependency, neural model, color estimator, line smoothing, edit-replacement or Forge integration change is included.

## Limits

This is a local heuristic for bright near-neutral surfaces, not a sparkle detector or semantic noise classifier. Intentional fine gray texture on such surfaces may be softened, and some diffuse glow/mottling may remain. Dark gray detail retains the existing conservative behavior. GPU and Windows Explorer end-to-end execution are not available in this Linux environment; their paths remain unchanged.
