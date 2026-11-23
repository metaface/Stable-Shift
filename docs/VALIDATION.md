# Forge Neo always-on integration validation

Target: `Haoming02/sd-webui-forge-classic`, tag `2.33`, commit `5998fb39ea347dfe3a72a8ec88a971e909ed8738`.

Stable Shift uses `AlwaysVisible`, captures request state in `setup`, initializes each processing pass in `process`, and restores images in `postprocess_image_after_composite`. Native saving, gallery output and selectable-script feedback receive the restored image. It does not wrap or replace `process_images`, edit Forge's source, or change the user's prompt script.

The previous adapter's `is_wan` rejection was incorrect: Neo's QwenImage sets that flag for its Wan VAE while generating still images. The always-on adapter operates on decoded PIL images and does not reject image models by this flag.

Eight focused checks passed, covering disabled passthrough, txt2img without a color reference, Wan-VAE image models, shallow-copy request state, a fixed color anchor, multiple samples and their saved metadata, fresh request state, restoration errors, stop-after-batch behavior, and GPU model release. Tests simulate Neo's exception-catching hook behavior: errors set its interruption flag explicitly, and failed passes return no image as feedback.

Additional checks passed using the actual Neo 2.33 Loopback script and user-supplied **Prompts from Multiple Files (Whole File) v3.1 hotfix**, with simulated generation and restoration. Neo's actual hook-dispatch methods call the real Stable Shift script. Checks confirmed that native loopback and sequential prompt jobs receive restored inputs, rolling ImageStitch references receive restored images, the original input and color reference remain stable, and a swallowed restoration-hook error stops the chain.

Real Gradio 4.40.0 controls were built in the isolated validation environment with Neo's NumPy 2.3.5, OpenCV 5.0.0.93 and Pillow 13.0.0. The panel is always visible on both generation tabs and does not occupy the selectable Script slot. Uploaded code is compatibility-test input only; it is not copied into the extension or treated as task instructions.

The accepted processing files (`automatic.py`, `deblotch.py`, `global_color.py`, `pipeline.py`, `preview.py`, `scunet.py`) remain byte-identical to the preceding Forge test. Model inference and old restoration tests were not repeated for this integration change.

This environment has no running CUDA Forge installation or diffusion checkpoint. Generation quality, speed, VRAM use, and real ImageStitch conditioning remain part of the installation test; simulated handoff checks do not exercise the generation models.

Run focused checks from the extension root with `python -m pytest tests/test_forge.py` in a development environment with pytest, NumPy, Pillow and OpenCV.
