# Forge Neo 2.33 integration validation

Target: `Haoming02/sd-webui-forge-classic`, tag `2.33`, commit `5998fb39ea347dfe3a72a8ec88a971e909ed8738`.

The adapter follows that release's selectable `Script.run`, `process_images`, `Processed`, image-saving, state, and memory-management interfaces. It does not patch Forge's source or use the user's custom loopback script.

Focused checks cover restored feedback ordering, a fixed reference, seed progression, grid exclusion, per-frame infotexts, generated/restored comparison files, cancellation/failure, restoration of caller settings, suppression of duplicate host color correction, and SCUNet memory release. They do not repeat the retired denoiser or line-processing tests.

The accepted automatic analysis, deblotching, color algorithms, and preview renderer are unchanged. The pipeline only gains an injectable denoiser so the adapter can manage Forge's GPU memory around the existing SCUNet inference. The extension removes the desktop GUI, desktop installer, and standalone package pins.

Runtime compatibility is checked separately with Neo 2.33's NumPy 2.3.5, OpenCV 5.0.0.93, Pillow 13.0.0, and Gradio 4.40.0. These packages are installed only in the isolated validation environment, never into the user's Forge by the extension.

Results: 12 adapter checks passed. The release's actual `Processed` constructor and JSON serializer accepted a two-frame adapter run. Real Gradio controls built with the expected defaults and callbacks. A retained 2048×2048 SCUNet result produced pixel-identical automatic restoration through the standalone and Forge processing entry points, with Robust global selected; model inference was not repeated.

This environment does not contain a running CUDA Forge installation or a diffusion checkpoint. Full generation speed, VRAM use, and visual behavior over real loops remain the purpose of the first user test.

Run adapter checks from the extension root with `python -m pytest tests/test_forge_loopback.py` in a development environment with pytest, NumPy, Pillow and OpenCV.
