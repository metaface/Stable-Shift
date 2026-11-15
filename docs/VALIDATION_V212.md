# V2.12 color regression correction

## Failure

V2.11 tried to recover tree shading using a spatial lightness residual between Classic and Robust global. Classic's field includes the local-cleanup baseline from before broad cleanup. Its residual therefore includes variation that the later cleanup deliberately removed. The coherence heuristic accepted some of that variation and returned blotches to the tail, shaded fur and denim.

The earlier fine-grain checks did not cover coherent contamination at those scales. A higher tree-contrast measurement did not demonstrate clean surfaces. V2.11's enhancement is withdrawn rather than retuned as part of this correction.

## Correction

Robust global is restored to the accepted V2.10 implementation. The global-color module and the engine's color-correction function match V2.10 exactly. The selected RGB transform acts directly on fully cleaned pixels. Its fit still uses the earlier baseline to estimate coefficients, but that is global parameter estimation, not a transfer of local residuals. The failed enhancement and its comparison path have been removed from runtime.

Classic, fallback behavior, denoisers, source tracing, automatic strength, local/broad cleanup, stroke cleanup and AA retain their accepted behavior. The tree's softer-looking shading remains an open issue. This version does not claim a replacement tree-shading fix.

## Regression evidence

A new synthetic case contains flat cleaned paint panels and a separate earlier baseline with smooth coherent blotches. Two new checks fail under V2.11:

1. Identical cleaned RGB pixels must remain a single corrected RGB color. V2.11 split one such flat color into thirteen output colors.
2. The complete Robust global color stage must exactly equal application of the fitted global RGB model, with no extra spatial detail added afterward.

Both pass after restoring the accepted implementation. The test checks more than one hundred flat-color groups, rather than only one selected patch. A repeated small-drift test also covers the complete color stage. Existing tests retain reference-grid, unrelated-reference fallback, line/stitch/smoke, quick-preview, signed-diagnostic, desktop and isolated-package coverage.

Full-size validation uses the supplied cabin and beach sources with their actual color references and verified cached CPU BM3D stages. Output is compared with the accepted V2.10 rendering at every RGB pixel. Surface crops include the tail, shaded leg, denim and tree, avoiding the previous focus on one contrast measurement. GPU and native Windows execution are unavailable; their adapters are unchanged.

Both Classic and Robust global match V2.10 with zero changed pixels on each full-size image. Robust global also matches the previously saved accepted outputs exactly. The complete test suite passes: 115 passed, 1 skipped because its historical fixture is unavailable. The standalone archive builds with 32 runtime files and excludes the withdrawn V2.11 validation document.
