# Stable Shift V2.25

Open an image and optionally a reference, then press **Run**. The reference supplies colors; it is not used to replace image details. Automatic strengths are enabled by default. No reference is required for denoising/deblotching.

## What Automatic does

The first analysis measures native high-frequency scatter away from strong edges where possible. This selects how much of the fixed SCUNet output is applied, including zero on quiet images. The real-PSNR model is a blind denoiser: its percentage blends the model output and input; it is not a learned noise-sigma control.

The selected denoised pixels go through the accepted independent regular/strong deblotching candidates. Surface analysis uses variation across scales, excluding coherent shading from estimation, plus a bright-texture cue. It chooses a global amount between 0 and 200. No analysis mask is used to copy noisy borders or texture back into the result. Bright texture is a heuristic, not a sparkle/halo classifier.

Reference correction uses the selected method and one frozen fit across all deblotching endpoints. Automatic applies the full fitted correction when a nontrivial change is needed; without a reference it applies zero. The result bar and saved report show effective values. Analysis can mistake intentional texture for noise; manual overrides remain available.

## Color methods

- **Robust global** fits one RGB transform to corresponding coarse colors. Its channel-mixing checks are normalized by overall exposure, so valid 0.1× darkening or strong brightening need not fail just because of scale. A stable fit is preferred when held-out color agreement matches or improves Classic; it must beat a flat-color guess. Clearly worse color errors, lost color variation and unstable channel mixing can still trigger Classic. The old fixed absolute-error and 50%-improvement rejection rules have been removed.
- **Classic** retains the accepted coarse LAB correction. It is also the explicitly reported fallback when Robust cannot fit a reliable mapping, including some references with different compositions.

The old Global palette statistics transfer is removed. Neither a new subtitle mask nor a new halo-repair pass is added. Classic retains its inherited local variation; it is not the uniform RGB model.

## Optional manual overrides

Uncheck **Automatic strengths**. The controls start at the applied values:

- **Denoise 0–100%**: zero skips the model; 100 uses its full output. Changing this requires Run and rebuilds the cleanup/color endpoints. Matching raw SCUNet inference is reused.
- **Deblotch 0–200%**: zero uses denoised pixels, 100 is the accepted regular filter, and 200 is the stronger independent candidate. Moving this updates from cache without repeating inference or cleanup.
- **Color correction 0–100%**: blends the chosen frozen correction. It is effectively zero when reference correction is off or no reference exists.

Changing reference or color method requires Run. A matching edited-image pixel signature gates model reuse. Saved settings describe the displayed result, even when a newer control edit is still pending. The backend API returns the same applied settings.

Use **Fit / 100% / 200% / 400%** result zoom and drag the zoomed result to pan. Saved PNGs always retain native dimensions. Inputs support file dialogs and native file drops, including paths with spaces and EXIF orientation.

## Saves and installation

**Save PNG + settings** writes the image and `.settings.json`. **Save test** writes an output folder containing `edited_source.png`, optional `color_reference.png`, `result.png`, optional `scunet_before_color.png`, and `settings.json`. A share archive prioritizes inputs/result and includes raw model output as space permits within 30 MiB. Extras remain in the folder.

Base requirements are Pillow, NumPy, OpenCV and tkinterdnd2. **SCUNet setup** reuses a working matching PyTorch runtime where possible; otherwise it installs matched official CPU or CUDA 12.8 wheels, then Spandrel 0.4.2. Restart after installation. The pinned official checkpoint is size/SHA-256 verified before atomic cache replacement. Model weights, `.venv` and user images are not tracked or included in the source ZIP.

SCUNet inference remains native-size float32 RGB with overlapping, phase-aligned tiles and reflected padding. CUDA memory exhaustion retries smaller tiles. An inference failure is reported rather than silently switching denoisers. Installation/device requirements are unchanged.
