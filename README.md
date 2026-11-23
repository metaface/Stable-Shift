# Stable Shift for Forge Neo

Stable Shift helps keep images clean and colors consistent during AI generation. It was made to reduce the noise, blotchy coloring, and color drift that can build up during repeated img2img edits, loopback generation, or generation with high step counts.

The extension cleans each generated image before Forge saves it. In a loopback workflow, that cleaned image becomes the next input, helping prevent small amounts of noise and color shift from accumulating over successive passes.

Stable Shift has its own panel on **txt2img** and **img2img**. You can use it for ordinary generation or alongside a script selected in Forge's **Script** dropdown.

## Installation

Stable Shift is designed for [Forge Neo 2.33](https://github.com/Haoming02/sd-webui-forge-classic/tree/2.33). Choose either installation method below.

### Install through Forge

1. Open Forge's **Extensions** tab.
2. Select **Install from URL**.
3. Enter these values:

   | Field | Value |
   | --- | --- |
   | URL for extension's git repository | `https://github.com/metaface/Stable-Shift.git` |
   | Branch name | `forge-neo-2.33-test` |

4. Click **Install**.
5. Restart Forge completely.

### Install from a ZIP

1. Open the [Stable Shift repository](https://github.com/metaface/Stable-Shift/tree/forge-neo-2.33-test) and select the **forge-neo-2.33-test** branch.
2. Choose **Code → Download ZIP**, or [download that branch directly](https://github.com/metaface/Stable-Shift/archive/refs/heads/forge-neo-2.33-test.zip).
3. Extract the ZIP.
4. Place the extracted extension folder inside your Forge installation's **extensions** folder and name it **Stable-Shift**.

   The folder layout should look like this:

   ```text
   <Forge folder>/
     extensions/
       Stable-Shift/
         scripts/
         stable_shift/
         README.md
   ```

5. Restart Forge completely.

Forge Neo supplies the required Python dependencies. The first time denoising runs, Stable Shift automatically downloads the official SCUNet model, approximately 72 MB, into `extensions/Stable-Shift/models/`.

## What the features do

### Denoising

Denoising removes fine grain and small pixel-level variations that can make an image look dirty. Stable Shift uses **SCUNet**, a trained image-denoising model, to produce a cleaner version of the generated image.

The denoise strength controls how much of that cleaned result is applied. Lower strengths retain more of the original texture.

### Deblotching

Deblotching reduces larger, uneven patches of color that can remain after fine noise has been removed. It is useful for surfaces that should look smooth but instead appear mottled or cloudy.

It uses an edge-preserving filter to smooth similar colors while limiting blending across edges. This cleanup is separate from SCUNet denoising, so its strength can be adjusted independently.

### Color correction

Color correction uses a reference image as a target for colors, brightness, and contrast. It helps keep the palette and lighting consistent when repeated generations gradually shift them.

Choose a reference in the **Color reference (optional)** section:

| Reference | What it uses |
| --- | --- |
| Starting image | The original img2img input, kept as the same color reference throughout the run. |
| Uploaded reference | A separate image uploaded in the Stable Shift panel. Available on both generation tabs. |
| Off | Denoising and deblotching without Stable Shift color correction. |

The default is **Starting image** for img2img and **Off** for txt2img. If no starting image is available, color correction is skipped.

**Robust global** is the default correction method. **Classic** is an alternative method you can try if you prefer its result.

### Automatic strengths

Automatic mode analyzes each generated image and chooses denoising, deblotching, and color-correction strengths. It is the recommended starting point for keeping manual adjustment to a minimum.

Uncheck **Automatic restoration strengths** to expose the manual controls:

| Control | Range |
| --- | --- |
| SCUNet denoise | 0–100% |
| Deblotch | 0–200% |
| Reference color correction | 0–100% |

A strength of **0** disables that stage's effect. Deblotching above **100%** applies stronger cleanup.

## How to use it

1. Open **txt2img** or **img2img** and configure your generation normally. Load your source image if using img2img.
2. Expand the **Stable Shift** panel and check **Enable Stable Shift**.
3. Leave **Automatic restoration strengths** enabled.
4. Choose a color reference if you want color correction.
5. Click **Generate**.

For ordinary generation, leave the **Script** dropdown set to **None**.

For loopback, select **Loopback** in that dropdown and configure its loop count and generation settings. Keep Stable Shift enabled in its separate panel. Each output is cleaned before Loopback uses it for the next generation.

Forge or the selected script controls prompts, seeds, batches, and loop counts. Stable Shift handles restoration of the resulting images.

## Saving and comparing results

The gallery shows restored images, and Forge's normal sample-saving settings apply to them.

Enable **Save generated/restored comparison files and report** to keep before-and-after copies. They are saved in a **stable-shift** subfolder inside the normal image output folder.

Each run contains matching files such as `0001-generated.png` and `0001-restored.png`, along with any starting image and color reference. A `report.json` file records the strengths, color method, seeds, and processing times. Compare the matching PNGs to see what the cleanup changed.

## Updating

For installations made through Forge, use **Extensions → Installed** to check for and apply updates, then restart Forge.

For ZIP installations, download the branch again and replace the extension folder with the newly extracted copy. Keep your existing **models** folder if you want to avoid downloading SCUNet again.

---

[Standalone application](https://github.com/metaface/Stable-Shift/tree/main-standalone)
