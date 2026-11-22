# Stable Shift for Forge Neo

An always-visible restoration panel for [Forge Neo 2.33](https://github.com/Haoming02/sd-webui-forge-classic/tree/2.33). Enable it on **txt2img or img2img**, then use normal generation, native Loopback, or another selectable script. It applies the accepted automatic SCUNet, deblotching, and optional reference-color correction to each generated image **before Forge saves or returns it**.

Stable Shift has its own panel, independent of the Script dropdown. The selected script controls prompts, seeds, batches, loop counts, and generation inputs. When that script uses a returned image as its next input or generated ImageStitch reference, it receives the restored image. The standalone application remains on `main-standalone`.

## Update the previous Forge test

From your **Forge folder** in Git Bash:

```bash
git -C extensions/Stable-Shift pull --ff-only
```

Restart Forge completely. The old **Stable Shift Loopback** dropdown entry is replaced by a permanent **Stable Shift** panel on both generation tabs. Existing model weights stay in place.

For a fresh install:

```bash
git clone --branch forge-neo-2.33-test --single-branch https://github.com/metaface/Stable-Shift.git extensions/Stable-Shift
```

Neo 2.33 supplies the dependencies; this extension does not install or downgrade them. The first SCUNet use downloads its verified official 72 MB checkpoint into `extensions/Stable-Shift/models`. You can also copy your existing `scunet_color_real_psnr.pth` there. [Official checkpoint source](https://github.com/cszn/KAIR/releases/tag/v1.0).

## Use

1. Open **txt2img** or **img2img** and configure generation normally.
2. Expand **Stable Shift** and check **Enable Stable Shift**.
3. Leave **Automatic restoration strengths** enabled for the first test.
4. Choose your normal script in the **Script** dropdown, or None for normal generation.
5. Click Forge's **Generate** button.

For native Loopback, select **Loopback** and start with three loops. For **Prompts from Multiple Files (Whole File) v3.1 hotfix**, select that script and use its normal progression controls. **Previous generated image** makes its next img2img job use the restored output; generated ImageStitch references also receive restored outputs. **Original input each step** keeps the original input, as that script specifies.

Stable Shift's color reference is optional and separate from the references used to guide generation:

- **Starting image**: fixed to the original img2img input for the request, including scripts that copy the processing object.
- **Uploaded reference**: use a separate image for color correction on either tab.
- **Off**: denoising/deblotching without Stable Shift reference-color correction. This is the default on txt2img.

If Starting image is selected without an img2img input, color correction is skipped; denoising and deblotching still work. Robust global and Classic retain the accepted implementations. While applying reference-color correction, Stable Shift bypasses Forge's img2img histogram correction within that processing pass and restores the original per-pass setting afterward. With Stable Shift color correction off, Forge's own color setting continues to apply normally.

Uncheck Automatic to expose SCUNet (0–100%), deblotch (0–200%), and color (0–100%) strengths. Automatic analyzes every generated image separately. Disabled Stable Shift leaves normal generation unchanged.

## Comparison files

With comparison saving enabled, the normal image output folder contains:

```text
stable-shift/<run-id>/
  00-input.png                 # when an img2img input exists
  00-color-reference.png       # when a color reference exists
  0001-generated.png
  0001-restored.png
  0002-generated.png
  0002-restored.png
  ...
  report.json
```

The report records each image's actual strengths, color method/fallback, model timings, seed, and input/output signatures. Restored PNGs include generation settings. These comparisons are independent of Forge's normal sample-saving setting. Zip the run folder to share it.

Restoration runs after inpainting compositing, on the final image, and before native saving and script feedback. Batches are supported; grids are assembled afterward and are not denoised again. Model-family flags such as Qwen's Wan VAE flag do not block still-image restoration.

Forge models are offloaded before CUDA SCUNet inference, and SCUNet releases its model afterward. Interruption or a restoration error stops further generation and removes the failed pass from returned feedback. Neo may still save an incomplete sample when an image hook is interrupted; its Stable Shift status is labeled Failed or Interrupted rather than Completed.

The numeric restoration core is unchanged. Compatibility checks use the actual native Loopback and uploaded prompt script with simulated generation, plus Neo 2.33's real hook dispatcher and Gradio controls. Full GPU generation remains an installation test. See [validation details](docs/VALIDATION.md).
