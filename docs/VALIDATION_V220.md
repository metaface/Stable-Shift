# V2.20 — full-strength SCUNet versus the accepted pyramid

The accepted V2.19 border fix remains the current deterministic method. This
experiment tests whether a learned denoiser can do better without the additional
guards, surface passes and stroke reconstruction.

## Model and runtime

The initial model is the authors' real-image PSNR variant, not the GAN variant.
The official [SCUNet repository](https://github.com/cszn/SCUNet) documents both
models and its [download script](https://github.com/cszn/SCUNet/blob/main/main_download_pretrained_models.py)
points to the authors' [KAIR release](https://github.com/cszn/KAIR/releases/tag/v1.0).
The RGB input convention follows the official real-image inference script.
[Spandrel](https://github.com/chaiNNer-org/spandrel) 0.4.2 supplies the model
architecture/loader; no network implementation is copied into this repository.

The checkpoint has 71,982,841 bytes and SHA-256
`fa78899ba2caec9d235a900e91d96c689da71c42029230c2028b00f09f809c2e`.
Downloads must match both before entering the cache. Dependencies are lazy and
optional. CPU/NVIDIA setup installs matching official PyTorch/torchvision wheels
only if a working matching runtime is absent, then the pinned Spandrel loader.
Loaded extension modules are verified in a fresh Python process. Base launcher
requirements and backend selection are unchanged.

Inference preserves native dimensions and RGB order. It uses float32, reflected
padding and overlapping native-scale tiles, not downsampled inference. Aligned
tile origins and raised-cosine weighting avoid hard stitching boundaries.
SCUNet can depend on wider context: the loader discourages tiling, and overlap
does not establish equivalence to a whole-image forward pass. The exported
report identifies actual tiles, device and GPU memory retries. No CPU/backend
fallback is performed for an explicit CUDA failure or an inference error.

## Comparison isolation

`Compare SCUNet` feeds only edited RGB pixels to the full model. It supplies
no masks, reference, noise ceilings, external cleanup or stroke fitting. Its
uncolored model output is exported verbatim as a PNG. The two denoised primary
views and the input control use the current live pipeline's single global
color transform, or all retain source colors if that fit is off/unreliable.
The current line strength affects only the accepted comparator. Pixel signatures
and options gate reuse of its cached preparation. If no matching cache exists,
the optional model is checked first so a missing runtime does not waste a
classical preparation.

The ordinary SCUNet dropdown option is different: it is a backend candidate
inside the existing source guards and local/broad cleanup. Sliders blend the
fixed model output, with exact zero/full endpoints. For this blind model, Auto
uses the requested blend ceilings and source-derived spatial permissions. It
does not use BM3D's sigma inversion, and skips a quiet image with no eligible
locations. The full model output is evaluated using the separate comparison.
Earlier non-SCUNet numeric processing is unchanged.

## Checks

Fixtures check tiled RGB identity across tiny/odd/multi-tile sizes, full model
replacement without source rescue, padding/coverage, invalid outputs, atomic
download verification, preservation of old cache files on network/checksum
failure, optional dependency errors and official installer command selection.
Pipeline integration checks full/zero model blending and report handling.

Comparison tests verify model-only pixels before/after shared colors, exact
accepted endpoints, one model call, cache reuse/rejection for changed inputs,
no classical run after model failure, and share-export contents. Desktop tests
exercise the actual Compare SCUNet action, setup reuse/failure and busy state.

Real inference validation uses the pinned official checkpoint on CPU. Accepted
V2.19 full-size views are independently saved controls, reused without changing
their pixels or color coefficients. The model outputs go through actual
comparison export. A smaller crop also compares whole-crop inference with forced
overlapping tiles to measure context sensitivity. Windows/CUDA execution is
unavailable here. This does not establish that a model trained for image
denoising will outperform the accepted method on every generated drawing.

The final Linux/Xvfb suite passes **248 tests**, with one historical real-image
fixture skipped because that file is unavailable. It also checks GPU memory
retry control without claiming a real CUDA execution. Ordinary app import and
cleanup run in a fresh process with Torch/Spandrel deliberately blocked.

The pinned checkpoint ran on all three 2048x2048 inputs, using CPU float32,
PyTorch 2.15.0+cpu and Spandrel 0.4.2. Each used 25 overlapping tiles. Observed
model times were 329 seconds for the cabin, 369 for the beach and 399 for the
alley on the shared two-thread validation CPU. These are not GPU speed figures;
cached comparator timings are not a fresh performance benchmark.

Every exported current view stays pixel-identical to its independently saved
V2.19 control, and every colored model view is exactly the saved raw model
output passed through the same frozen color transform. A separate replay of
accepted native/coarse layers through current preparation matches V2.19 at
0, 25, 50, 100 and 200 percent for all three cases. Input signatures match.

On a 384x256 cabin crop, a whole-crop forward pass versus forced 256-pixel
overlapping tiles differs by mean absolute RGB 0.009/255, maximum 1/255, with
99 percent of channel values identical. This is a crop-specific context check,
not a general guarantee of tiled equivalence. The actual model-only outputs
remain visually reviewable alongside native crops and source controls.

All three share bundles fit within 30 MiB. The beach bundle omits the redundant
full-size input color control while retaining the compared images, original
inputs and raw model output; all extras remain in its full folder. The small
standalone archive contains 48 runtime/documentation files, not model weights,
Torch or test images.
