# Stable Shift for Forge Neo

Stable Shift cleans generated images by reducing fine noise and blotchy colors. Optional color correction matches the image's colors and brightness to a reference.

It appears as a **Stable Shift** panel on both **txt2img** and **img2img**. Restoration runs before Forge saves the image or passes it to another generation, so it works with normal generation, Loopback, and sequential prompt scripts.

## Installation

Requires [Forge Neo 2.33](https://github.com/Haoming02/sd-webui-forge-classic/tree/2.33).

From your Forge folder, run:

```bash
git clone --branch forge-neo-2.33-test --single-branch https://github.com/metaface/Stable-Shift.git extensions/Stable-Shift
```

Restart Forge completely.

Forge provides the required Python dependencies. The first use of SCUNet automatically downloads its official 72 MB model to:

```text
extensions/Stable-Shift/models/scunet_color_real_psnr.pth
```

You can also place an existing copy of that model there. Stable Shift verifies the file before loading it. [Model download](https://github.com/cszn/KAIR/releases/tag/v1.0).

## Quick start

1. Open **txt2img** or **img2img** and configure your generation.
2. Expand the **Stable Shift** panel and check **Enable Stable Shift**.
3. Leave **Automatic restoration strengths** enabled.
4. Choose a color reference if you want color correction.
5. Click **Generate**.

For ordinary generation, leave the **Script** dropdown set to **None**. You can select another script while keeping Stable Shift enabled.

## Restoration controls

Automatic mode analyzes each generated image and chooses its restoration strengths. This is the recommended starting point.

To set strengths yourself, uncheck **Automatic restoration strengths** and expand **Manual restoration strengths**.

| Control | Range | What it does |
| --- | --- | --- |
| SCUNet denoise | 0–100% | Reduces fine noise using the SCUNet model. |
| Deblotch | 0–200% | Reduces uneven patches of color. Values above 100% use stronger cleanup. |
| Reference color correction | 0–100% | Controls how much reference-color correction is applied. |

A strength of 0 disables that stage. Color correction requires an active color reference. Automatic analysis can also respond to intentional grain or texture; use manual controls when you want to retain more of it.

## Color references

The color reference guides restoration colors. References used to guide AI generation, such as ImageStitch references, are configured separately.

| Color reference | Use |
| --- | --- |
| Starting image | Matches the original img2img input. The reference stays fixed throughout the run. |
| Uploaded reference | Uses a separate image uploaded in the Stable Shift panel. Works with txt2img and img2img. |
| Off | Runs denoising and deblotching without Stable Shift color correction. |

The default is **Starting image** on img2img and **Off** on txt2img. If no starting image is available, Starting image skips color correction.

**Robust global** is the default color method. **Classic** provides an alternative. Saved settings record the method actually used, including any fallback.

While Stable Shift applies reference-color correction, it bypasses Forge's own img2img histogram correction for that processing pass to avoid applying both. With Stable Shift color correction off, Forge's color setting applies normally.

## Loopback and prompt scripts

Stable Shift handles restoration; the script selected in Forge controls prompts, seeds, loop counts, batches, and generation inputs.

### Native Loopback

1. Enable Stable Shift.
2. Select **Loopback** in the **Script** dropdown.
3. Set the loop count and denoising settings in Loopback.
4. Click **Generate**.

Each generated image is restored before Loopback uses it as the next input.

## Saved images and comparisons

Forge's normal gallery and sample-saving settings apply to restored images. Stable Shift processes individual images before grids are assembled.

Enable **Save generated/restored comparison files and report** to save before-and-after pairs under the normal image output folder:

```text
stable-shift/<run-id>/
  00-input.png                 # if an img2img input exists
  00-color-reference.png       # if a color reference exists
  0001-generated.png
  0001-restored.png
  0002-generated.png
  0002-restored.png
  ...
  report.json
```

Compare matching generated/restored files to inspect the cleanup. The report contains strengths, color methods, seeds, and timings. Restored PNGs include generation settings. Comparison saving works independently of Forge's normal sample-saving setting.

If restoration fails or is interrupted, further generation stops and the failed pass is excluded from script feedback. Forge may save an incomplete sample labeled **Failed** or **Interrupted** in its Stable Shift settings. Check the Forge console and `report.json` for details.

## Updating

From your Forge folder:

```bash
git -C extensions/Stable-Shift pull --ff-only
```

Restart Forge after updating.

---

[Standalone application](https://github.com/metaface/Stable-Shift/tree/main-standalone) · [Development and validation](docs/VALIDATION.md)
