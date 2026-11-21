# Stable Shift

**V2.24** keeps one restoration workflow: image analysis, SCUNet denoising, deblotching and reference color correction. Automatic strengths are on by default. Manual overrides are optional.

Close the app, update your Git checkout, then double-click **START_Stable_Shift.bat**. Git removes the retired tracked scripts; your existing `.venv`, model cache and images remain in place. A fresh ZIP should be extracted into a new folder.

1. Open or drop the image to restore.
2. Optionally open a color reference.
3. Leave **Automatic strengths** enabled and press **Run**.

The result bar shows the actual strengths and color method. **Save PNG + settings** writes the native image and applied settings. **Save test** exports the inputs, result and analysis, with a share ZIP within 30 MiB when possible.

## Automatic and manual control

Analysis estimates fine scatter and remaining surface variation. It can skip denoising on quiet inputs, use full SCUNet on noisy ones, and choose stronger deblotching for textured bright surfaces. These measurements select amounts of the accepted operations; they do not paint protected borders or restore source noise around lines. Intentional texture can affect the estimate.

Uncheck **Automatic strengths** to expose **Denoise 0–100%**, **Deblotch 0–200%**, and **Color correction 0–100%**. Manual values start at the applied automatic settings. Deblotch and color update from cached pixels. Denoise or color-method changes require Run, reusing matching SCUNet inference.

**Robust global** is the default color method, with an explicitly reported **Classic** fallback. Classic remains selectable. Robust now evaluates color mixing relative to overall exposure, allowing legitimate strong darkening/brightening. It still validates color agreement; a different composition can require Classic. The experimental Global palette transfer has been removed.

## SCUNet setup

Existing SCUNet installations are reused. For a new installation, use **SCUNet setup → NVIDIA GPU** or **CPU**, then restart. The official real-PSNR model is downloaded and checksum verified in `models/`. Optional PyTorch/Spandrel remain separate from base dependencies and the small standalone ZIP. CPU inference can take minutes on large images.

## Current scope

BM3D/NLM, source guards, pyramid/line reconstruction, antialiasing, Preserve Edits, old comparison buttons/scripts, historical validation files and their unused tests have been removed from this branch. Existing Git history retains prior versions. No new halo-repair operation is included.

See [the user guide](docs/STANDALONE.md) and [focused validation](docs/VALIDATION.md). Core processing is available separately from Tk through `stable_shift.pipeline` for later Forge integration.
