# V2.24 focused validation

Only the retained path is tested: automatic analysis, SCUNet integration, deblotching, reference color, cached manual previews, exports and the desktop flow. Historical BM3D, Edit, line reconstruction and AA tests are removed with their unused code.

The small retained suite has ten focused checks. It covers exposure-aware fitting at 0.1× and 6×, rejection of unrelated color fits, quiet/noisy/gradient analysis, exact quiet-image preservation without loading optional model dependencies, model reuse gated by pixel signatures, reversible cached blending, actual applied saves/share inputs, absence of retired modules, and desktop automatic/manual/failure/stale-worker behavior. Linux/Xvfb was used; Windows/CUDA execution is unavailable here.

Cached actual 2048×2048 SCUNet outputs are reused for the cabin, beach and alley. The unchanged inference implementation is not repeatedly rerun for a color/cleanup refactor. Accepted manual cleanup endpoints at 0, 100 and 200 remain pixel-identical. The extracted Classic fitter also matches the earlier accepted Classic output exactly, despite removal of its old Edit-engine dependency.

Automatic recommendations on those fixtures are:

| Image | Denoise | Deblotch | Color |
| --- | ---: | ---: | ---: |
| Cabin | 100 | 100 | 100 |
| Beach | 100 | 200 | 100 |
| Alley | 100 | 85 | 0 (reference disabled in this fixture) |

The original warm alley reference remains available only inline in the conversation. Classic extraction is instead compared with a clearly labeled controlled dark-reference result. This is not an exact replay of that original reference pair.

Robust fitting now factors a positive fitted exposure scale out of its singular-value checks. Relative channel mixing, determinant, conditioning, held-out agreement and comparison with a constant-color prediction still constrain acceptance. Strong darkening alone no longer fails the fixed minimum-gain check. The model's actual coefficients are not changed when an existing fit already passes.

Automatic analysis is a heuristic, not semantic certainty about texture. Fine scatter sets denoise blending. Medium-scale variation outside strong/coherent edges sets regular deblotching; supported bright fine texture can raise its recommendation toward 200. Color fitting is evaluated on the denoised baseline and frozen across manual cleanup previews. No wide source protection, dirty-border copy-back, new line fitter, or experimental halo painting is applied.

The simplified UI was inspected at its normal and minimum window sizes. The standalone package contains only the current runtime and short user documentation. Optional model weights and test images are excluded. Git updates remove retired tracked files while leaving ignored user data/model caches in place.
