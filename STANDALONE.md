# Difference Guard v1.1 — Restoration Lab (experimental)

Standalone Windows test build. Keep v1.0 separately. No Forge changes, AI generation, model weights, or edit-mask redesign.

## Start

1. Extract this folder outside Forge. Use 64-bit Python 3.11 or 3.12 with Tkinter (python.org installer).
2. Double-click START_Difference_Guard.bat. First launch installs the basic dependencies into this folder's .venv.
3. Click **Install CPU BM3D** once, or **Install GPU BM3D (CUDA 12)** for the experimental NVIDIA backend. Both install into this app's interpreter; restart after installation if necessary. Internet is required. GPU dependencies can be large.
4. Load the clean color reference and edited image. Restore Quality permits different sizes; the output retains the edited dimensions.
5. First compare v1.0 and CPU BM3D here with identical noise/guard settings and cleanup at 0. Then compare GPU BM3D at the same settings. Try cleanup at 25–50 only after establishing those baselines.

**The reference supplies color correction only in Restore Quality.** It does not guide edges, denoising, or cleanup; no reference details or pixels are copied. The inherited global LAB palette estimator is retained in this release, not replaced with a claimed perfect matcher. It can still leave cream fur or muted blue denim and can recolor intentional lighting changes. A structurally different image is not pixel-perfect ground truth.

## What's new

- System/Light/Dark theme selector. System follows Windows AppsUseLightTheme and refreshes while open. Non-Windows detection defaults to dark; override manually. Native file dialogs follow OS settings.
- Live elapsed timer; completed analysis/denoise, cleanup, color correction, and total processing seconds. Timings exclude loading, preview drawing, and saving. First GPU run includes CUDA initialization/compilation. Compare warm runs separately from first runs.
- Explicit **CPU BM3D** and experimental **GPU BM3D** choices. GPU errors stop the run and do not silently fall back to CPU. CPU remains available.
- Optional **chroma cleanup**, off by default. Six short, bounded LAB chroma-diffusion steps, guided by the denoised edited image's luminance/chroma boundaries. Luminance stays fixed in LAB; RGB conversion/quantization can cause small numerical changes. Corrections are capped. This is not a semantic detector or a guarantee that every blotch is removed. It can suppress intentional color texture; compare against off.
- **Color only** baseline; NLM and boundary-constrained retained for comparison. BM3D/NLM still use inherited post-denoise edge blending; their internal algorithms have not been modified to accept barriers.
- PNG Save also writes a .settings.json with actual run settings and timings. Comparison exports full-resolution outputs, a reduced comparison sheet, three matching 256-pixel native-resolution crop sheets, settings and per-backend timing reports. Crops use fixed normalized locations, not semantic detection.
- Analysis boundaries no longer use the clean reference in Restore Quality.

## GPU details and troubleshooting

Uses documented `bm3d_cupy.bm3d_gpu` from pinned bm3d-cupy 0.1.3, installed with its cuda12 extra. CPU and GPU process normalized LAB channels independently with corresponding noise settings, but are different implementations and need visual comparison. Both run the inherited edge-protection blend afterward.

A CUDA-capable NVIDIA card and compatible driver/runtime are necessary. The RTX 5080 has **not** been validated in this environment. CuPy's CUDA libraries do not replace your NVIDIA driver. If GPU installation or execution fails, retain the error and select CPU BM3D. Do not install a second CuPy variant into the same environment. No automatic system driver installation occurs.

The install button allows up to 20 minutes for large dependency downloads. A running CPU/GPU job cannot be cancelled gracefully in this build; closing the application ends its worker. Keep the old installation and source images intact.

The CPU BM3D package publishes noncommercial license terms; review them before use. Review the GPU package's separate license/dependency terms as appropriate:
- https://pypi.org/project/bm3d/
- https://pypi.org/project/bm3d-cupy/
- https://github.com/kvttt/bm3d_cupy

## Scope and validation

Preserve Edits is the unchanged legacy task, requires same-sized registered images, and is deferred. Its sensitivity slider applies only to that task. Restore Quality does not invoke its edit detector. No SCUNet/neural model, negative-clarity luminance stage, or automatic blotch classifier was added.

Seven automated checks passed on Linux: existing size/registration safeguards and boundary denoising, plus reference-independence with color disabled, chroma cleanup/luminance tolerance, actual CPU BM3D noise reduction, timing reports, and explicit GPU dependency failure. The optional real-image test is a no-op when its historical local image is absent; no claim is made that the user's original pair was processed here.

Python syntax compilation passed. Tkinter GUI launch was attempted but this executor has no display server; live GUI interactions and Windows theme detection remain unverified. GPU execution and RTX 5080 performance remain unverified. This is a test build, not a promise of improved image quality over v1.0.

Run checks after installing CPU BM3D and pytest: `python -m pytest -q test_engine.py test_v11.py`.
