# V2.14 line-border comparison

## Problem and scope

V2.13's quarter/half/full reconstruction is preferred, but light noisy paint remains around ink. The accepted source tracer expands linked gradient edges by one pixel to include stroke centers. That shared mask therefore includes both ink and adjacent paint. The pyramid restores the entire native working band after rebuilding its surfaces. Local cleanup/automatic fades can also retain variation near lines upstream.

V2.14 tests a dedicated correction on the preferred pyramid. Normal Run, color fitting, denoiser adapters, tracing, automatic estimation, accepted local/broad cleanup, AA and optional stroke cleanup are unchanged. Existing V2.13 comparison outputs remain unchanged. Shared preparation and pyramid-field helpers are factored out so both tests use the same layers rather than rerunning separate variants.

## Candidate

Two-sided RGB cross-sections locate darker ink within the original source evidence. The darkest central profile portion supplies a narrower measured-ink mask. Ink color comes from the actual native working image; it is not replaced with black.

For nearby paint, rays point away from the nearest measured ink pixel and stop at another measured stroke. Three coarse-field samples at distances 3, 5 and 7 supply same-side paint. Two valid samples are required. A gentle consistent RGB trend can be extrapolated back to the target, with a bounded adjustment, to preserve shading next to a line.

An observed-ink/clean-paint RGB model estimates coverage. Old wide-core pixels below strong ink coverage can have their color projected onto that local model, removing off-color contamination without explicit along-stroke opacity smoothing. Outside the old core, only paint-like pixels receive cleanup, without returning a native opacity residual. Measured ink and stronger coverage retain their existing RGB.

The full candidate reaches six native pixels from measured ink. It has full effect on the adjacent paint and fades only at its outermost pixel. Color/profile limits reject large incompatible replacements. The before/after shares one global RGB transform; an unreliable fit leaves both in source colors. The native source/reference color roles are unchanged.

This intentionally changes paint/edge pixels inside the old source mask. Comparing every old-core pixel for equality would reject the requested fix. The report instead records old-core changes, measured-ink equality, exact signed RGB change, and support/coverage maps. Measured-ink equality does not prove preservation of every actual stroke.

## Validation

Independent synthetic fixtures contain known colored and faint ink, light noisy fringes inside the old wide core, clean and contaminated antialiased edges, curved strokes, stitch gaps, opposite paint colors, clean paint gradients, narrow gaps, broad shade steps and bright details. Tests require substantial fringe-error reduction, unchanged known ink, retained clean coverage, reduced contaminated edge-color error, unchanged clean shading, and no sampling through another stroke. Tiny/no-ink, strength-zero and invalid settings are covered.

Full-size supplied cabin, beach and alley inputs use verified native CPU BM3D candidates and previously executed independent quarter/half CPU layers. Replays check the original input pixels, exact backend arguments, independent source reductions and all coarse processing options before reuse. The previous pyramid must match the saved V2.13 output at every RGB pixel. The actual references are used for cabin/beach; alley reference correction is off because the original warm reference is unavailable as a file. No new production cache interface is added.

The corrected native bib crop reduces the pocket/waist fringe, including off-color edge pixels. Full-image changed-pixel counts and observed-ink equality are recorded; they are not percentages of noise removed or semantic preservation scores. The control rendering has zero changed RGB pixels in all three cases, and measured ink has zero changed pixels before/after shared color correction.

| Input | Old wide-core pixels changed | Measured ink pixels changed |
| --- | ---: | ---: |
| Cabin | 323,296 | 0 |
| Beach | 443,932 | 0 |
| Alley | 404,779 | 0 |

Every pyramid, solid and gradient output in the retained V2.13 comparison also matches its previous rendering at every RGB pixel after the shared-helper refactor. The eighteen retained processing modules outside the experimental reconstruction/UI files are byte-identical to V2.13.

The native Tk comparison worker/export, full-image share ZIP, common finishing-off settings, independent scale calls, original Run result retention, existing processing regressions and isolated package checks are retained. GPU and native Windows execution are unavailable here; their adapters/installers and dependencies are unchanged.

Final suite: **147 passed, 1 skipped** because the historical real-image fixture is unavailable. The standalone archive includes thirty-seven runtime/documentation files and excludes tests and user/validation images.

## Limits

This is a local profile/matting approximation. Tight gaps can be left unchanged when paint cannot be sampled without crossing ink. Ambiguous low-coverage pigment, tiny colored details or highlights can be mistaken for paint. Source ink texture, broken geometry and misclassified traces are not guaranteed to improve. The candidate stays isolated in Compare line borders until reviewed visually.
