# Stable Shift for Forge Neo — first loopback test

An img2img loopback extension targeting [Forge Neo 2.33](https://github.com/Haoming02/sd-webui-forge-classic/tree/2.33). Each generation passes through the accepted Stable Shift V2.25 restoration pipeline: automatic analysis, SCUNet real-PSNR, deblotching, and reference color correction. The **restored pixels become the next loop's input**.

This branch contains the Forge extension. The desktop application remains on `main-standalone`.

## Install this test

Update Forge Neo to 2.33 first. From your **Forge folder** in Git Bash:

```bash
git clone --branch forge-neo-2.33-test --single-branch https://github.com/metaface/Stable-Shift.git extensions/Stable-Shift
```

Restart Forge completely. The repository is private, so Git may ask you to sign in with an account that has access. No separate virtual environment or package installation is needed: Neo 2.33 already provides Torch, Spandrel, NumPy, OpenCV, and Pillow. This extension does not install or downgrade them.

The first SCUNet use downloads the official 72 MB checkpoint into `extensions/Stable-Shift/models`. You can also copy your existing `scunet_color_real_psnr.pth` there; its checksum is verified before use. [Official checkpoint source](https://github.com/cszn/KAIR/releases/tag/v1.0).

To update this test later:

```bash
git -C extensions/Stable-Shift pull --ff-only
```

Restart Forge after updating.

## First test

1. Open ordinary **img2img** and load a starting image. Use your usual prompt/model and generation settings.
2. Set Forge **Batch size = 1** and **Batch count = 1**.
3. In the **Script** dropdown, select **Stable Shift Loopback**.
4. Start with **3 loops**, **Automatic restoration strengths** checked, and **Starting image** as the color reference.
5. Leave comparison saving enabled and click Forge's normal **Generate** button.

The gallery contains the restored result of each completed loop, in order. Forge's img2img denoising strength stays constant. The seed increments by one per loop unless you choose Fixed. The last loop is restored too.

The same starting image is the color reference throughout the chain. You can instead upload a separate reference, or select Off. Robust global and Classic use the same accepted standalone implementations, including reporting an actual fallback. Forge's own automatic img2img color correction is bypassed within this script to avoid applying two corrections; its global setting is not changed.

Uncheck Automatic to expose manual SCUNet (0–100%), deblotch (0–200%), and reference correction (0–100%) controls. Automatic analyzes each newly generated frame separately. It estimates noise and surface variation; intentional grain and small details can affect those estimates.

## Comparison files

With comparison saving enabled, the img2img output folder contains:

```text
stable-shift/<run-id>/
  00-input.png
  00-color-reference.png       # when enabled
  01-generated.png
  01-restored.png
  02-generated.png
  02-restored.png
  ...
  report.json
```

`report.json` records per-loop automatic strengths, color method/fallback, model timings, seeds, and pixel signatures. A loop's feedback signature should equal the next loop's generation-input signature. Restored PNGs include generation settings. These files are enough to diagnose the first test; zip the run folder if sharing it.

Normal restored samples also follow Forge's sample-saving settings. Feedback uses the in-memory restored image, so saving samples as JPEG does not add JPEG degradation to the loop. Comparison saving is independent of normal automatic sample saving.

Interrupt discards a restoration that has not finished, and returns already completed restored frames. Stop after the current batch lets that generated frame finish restoration, then stops the chain. A restoration failure stops the run and reports the error, rather than feeding the uncorrected generation forward.

## Scope of this first test

This version supports one chain of ordinary still-image img2img generations. Inpainting and multiple-image batches are rejected with an explanatory message. It uses neither the native Loopback script nor a custom loopback script. Progressive lighting controls and additional line processing are outside this test.

Forge offloads its diffusion models before SCUNet uses CUDA. SCUNet releases its model afterward so Forge can resume generation; the checkpoint stays cached on disk. CPU Forge uses CPU SCUNet. The adapter has focused integration checks against Neo 2.33's interfaces; a complete GPU loop still needs testing in your Forge installation. See [validation details](docs/VALIDATION.md).
