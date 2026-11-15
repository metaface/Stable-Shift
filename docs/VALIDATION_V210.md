# V2.10 stroke cleanup validation

## Scope and strength

The accepted denoisers, automatic-strength controller, source tracing, local/broad surface cleanup and V2.9 color transforms are unchanged. Stroke cleanup is an optional finishing stage after color and before AA. It is off by default for normal processing; enabling it starts at **100**, the full candidate. Compare strokes always tests **0, 60 and 100**, with the same upstream result and AA off. No automatic controller reduces this finishing strength.

The source map locates possible stroke regions. RGB cross-sections distinguish darker ink from an ordinary step boundary. The renderer estimates stroke direction and cross-section center, follows a curved path up to nine pixels in each direction, aligns corresponding profile positions and chooses an observed RGB sample from the darker quarter. This favors intact ink over pale cuts. Its local RGB compatibility range scales with measured stroke contrast, limiting borrowing from unrelated nearby colors. Short strokes reject background samples so surrounding blue does not erase the stitches. Candidate pixels receive the full repair at 100; the source mask is an application guide rather than a protection veto during this finishing stage.

This is profile cleanup, not a complete vector reconstruction. It can strengthen, thicken or alter small strokes, especially near corners, tiny texture and intersections. Entirely missing long segments and arbitrary intentional dash patterns are not reliably reconstructed. The reference supplies color correction only; the stroke renderer never receives the reference image. No fixed black paint is used.

## Meaningful regression checks

Synthetic tests require full-strength cleanup to reduce colored grid cuts in a continuous stroke by at least 75% while retaining differently colored ink and blue gaps in a stitch pattern. A curved colored stroke is compared with its undamaged target; cleanup must improve the damaged result. White texture beside a sharp dark contour must not borrow black specks. A broad smoke/shading step remains byte-identical.

Other checks establish an exact zero bypass, literal 60% blending of the full candidate, validation before backend execution, actual changes inside the carried source map, and no changes outside that map. Full pipeline and quick-preview signed maps satisfy `denoise + cleanup + palette + stroke + antialias = total`. Stroke and AA previews can be mixed without accumulating filtering, losing upstream settings, or rerunning the backend. Turning both finishing stages off recovers exact post-color pixels.

Comparison tests count one backend run, hold colors fixed, force AA off, and match the 0/60/100 exports against their corresponding normal Run results. Native Tk tests exercise the new comparison and preview workers, the initial strength of 100, input-cache clearing and actual settings metadata. Existing color and auto comparisons disable both finishing stages even if requested controls are nonzero. Packaging retains isolated execution and repeatable archives without new dependencies.

## Full-resolution evidence

Previously executed CPU BM3D candidates were replayed with exact source-pixel and backend-argument checks. With stroke cleanup disabled, the accepted cabin, alley and beach outputs remained byte-identical: zero changed RGB pixels. The supplied cabin and beach pairs also retained the exact V2.9 Robust global color output before stroke cleanup. The four analysis/tracing/cleanup modules and the global color module remain byte-identical to V2.9; backend/edit functions are unchanged.

The final renderer was then applied to those actual 2048×2048 post-color results with the corresponding source maps. One local CPU timing per input was:

| Input | Pixels changed at 100 | Mean absolute RGB change on candidate pixels | Stroke time |
| --- | ---: | ---: | ---: |
| Cabin | 4.60% | 7.68 /255 | 9.12 s |
| Alley | 5.07% | 3.81 /255 | 9.16 s |
| Beach | 6.38% | 9.82 /255 | 8.81 s |

These numbers prove applied pixel changes, not restoration accuracy or noise-removal percentages. Stroke time excludes upstream processing and export; hardware and run-to-run timing vary. Full images and native crops at 0/60/100 were inspected. Ink changes are visible, including heavier line weight at full power; small imperfections remain. The alley check uses its accepted color-off output because its actual warm reference is available only inline in the conversation. No claim is made about a new real-alley color fit.

Native Windows and GPU execution are unavailable in this development environment. The GPU adapter is unchanged. The historical absolute-path image-fixture test remains skipped when that fixture is absent.
