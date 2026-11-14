# V2.4 validation

## Scope

V2.4 changes the extra blotch pass from V2.3. The V2.1 source-line tracer, local sampler, legacy palette/core, edit detection, BM3D adapters and dependencies are byte-identical to the accepted V2.1 files. The frozen-palette wrapper and comparison export from V2.3 are retained. V2.2's unmerged palette experiment is excluded.

The regional quadratic is now only a detrending aid. A normalized, native-resolution local residual estimate is added back, so wider nonlinear shading is retained. A 12-pixel smooth boundary taper limits contrast changes near protected lines. Local confidence no longer becomes almost certain just because the user selects LAB similarity 40. Requested corrections are capped at 3 LAB units before RGB conversion; final RGB channels stay within the observed 49×49 source neighborhood envelope.

## Automated checks

Run under an available desktop/display:

```text
DISPLAY=:100 OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 python -m pytest -q
```

The suite covers CPU BM3D, explicit GPU failures, source-line linking/propagation, reference independence, local cleanup, stage accounting, palette equivalence, native Tk file drops, themes, saved settings and both GUI workers. The historical fixture test remains skipped when its old local fixture is absent.

**51 passed, 1 skipped** in the final full suite.

New regression checks cover nonlinear shadows, repeated processing of clean shading, bounded local output colors, and the immediate surroundings of a weak protected stroke. The saved-pair replay is tested with and without an actual source mask.

Controlled results:

- Correlated blotches on a known clean shaded surface: RGB MSE **38.112 → 14.846 at 70** (61% reduction), and **→ 9.053 at 100** (76% reduction). These are synthetic error reductions, not percentages of noise removed from the supplied artwork.
- A clean quadratic-shading control stays byte-identical through five passes.
- A clean nonlinear shadow at strength 100/range 40 retains **23.927 of its original 23.975 LAB-L contrast**; mean brightness change is 0.441 LAB-L.
- Weak protected stroke pixels remain exact, with at most one RGB level of change in the tested three-pixel surroundings.

## Supplied V2.3 comparison

Used the user's native 2048×2048 `00_v21_before_palette.png` and `01_broad_before_palette.png`, and read the JSON settings as data. The original settings were GPU BM3D 100/100, local cleanup 100, LAB range 40, brightness cleanup 100, broad maximum 100. This executor has no GPU; the saved shared baseline lets us isolate the extra stage without replacing the user's denoiser run.

The actual original source-core mask was not in the supplied ZIP. The replay freezes **all unchanged pixels from the submitted pair**: 24.646% of the image. This includes every originally protected pixel plus some quiet pixels. It is stricter than the original 13.153% mask, and can understate cleanup. It does not establish an exact end-to-end rerun.

At maximum 100, the local candidate:

- Takes about **6.1 seconds** on this development CPU.
- Changes 36.884% of pixels, with a mean absolute RGB change of 0.375/255.
- Changes **zero** pixels in the conservative frozen set.
- Produces **zero** output pixels with a channel outside the observed 49×49 source envelope. The submitted V2.3 result had 278,880 such pixels; that count is not a count of visible black dots.
- Has native pre-palette L changes from **−2.417 to +2.545**, versus V2.3's **−13.654 to +15.210**.

Native crops of denim, background trees, cabin/window, foreground-tree shading and the eye were visually inspected. The candidate keeps wider shading and avoids the abrupt added rims and eye patches seen in the submitted V2.3 output; remaining blotches are visible. A display approximation derived from the submitted before/after palette pair was used for additional visual inspection only. All measurements above use the actual pre-palette pixels; the original palette field cannot be recovered exactly from the supplied PNGs.

To replay an extracted comparison without rerunning BM3D:

```text
python validate_blotch_pair.py --input "PATH/comparison" --out "PATH/replay"
```

Optionally add `--source-mask "PATH/shared_source_line_core.png"` from that exact run. With no mask, the conservative unchanged-pixel superset is explicitly recorded. The tool exports a pre-palette candidate and JSON report; it does not reconstruct an original input or apply an estimated palette.

## Full-resolution beach control

Reused the previously computed 2048×2048 CPU BM3D/V2.1 local-cleanup baseline and **actual original source-core mask** from the two supplied beach inputs. No generative output or additional character reference was used as ground truth. The original inputs/artwork are not committed.

Both variants use the actual V2.1 frozen field. Its baseline output again matches the original V2.1 palette function byte-for-byte.

| Broad maximum | Stage time | Pixels changed | Mean RGB change /255 | Changed core before/after palette | Max RGB change within 3 px of core |
| --- | --- | --- | --- | --- | --- |
| 70 | 6.37 s | 27.108% | 0.231 | 0 / 0 | 1 |
| 100 | 5.95 s | 32.172% | 0.345 | 0 / 0 | 1 |

Times cover the extra CPU stage, not BM3D or export. Native fur crops were inspected. Cleanup is modest and existing sparkle halos remain. GPU execution and Windows Explorer end-to-end behavior are not verified in this Linux executor; the existing adapters/dependencies are unchanged.

Exact protected RGB and bounded local colors are useful constraints, not proof that all real linework, artistic shading or texture is classified correctly. The next visual comparison remains necessary before merging this test.
