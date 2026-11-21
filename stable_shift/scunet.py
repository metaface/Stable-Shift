"""Optional official SCUNet real-PSNR model, with native-size tiled inference.

Torch/Spandrel are imported only when selected. Model-only inference never uses
source masks, palette references, local cleanup or stroke reconstruction.
"""
from hashlib import sha256
import math
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import RLock
from time import perf_counter
from urllib.request import Request, urlopen

import numpy as np

MODEL_NAME = 'scunet_color_real_psnr.pth'
MODEL_URL = 'https://github.com/cszn/KAIR/releases/download/v1.0/'+MODEL_NAME
MODEL_BYTES = 71982841
MODEL_SHA256 = 'fa78899ba2caec9d235a900e91d96c689da71c42029230c2028b00f09f809c2e'
SPANDREL_PACKAGE = 'spandrel==0.4.2'
_LOCK = RLock()
_MODELS = {}


def model_path():
    return Path(__file__).resolve().parent.parent/'models'/MODEL_NAME


def _digest(path):
    digest = sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_weights(path=None, progress=None):
    """Cache the official, checksum-pinned weights using an atomic download."""
    path = model_path() if path is None else Path(path)
    if path.is_file() and path.stat().st_size == MODEL_BYTES and _digest(path) == MODEL_SHA256:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        if progress:
            progress('SCUNet: downloading official real-PSNR weights (72 MB)')
        with NamedTemporaryFile(dir=path.parent, prefix=MODEL_NAME+'.', suffix='.part', delete=False) as output:
            temporary = Path(output.name)
            request = Request(MODEL_URL, headers={'User-Agent': 'Stable-Shift-SCUNet'})
            with urlopen(request, timeout=60) as response:
                received = 0
                while chunk := response.read(1024*1024):
                    received += len(chunk)
                    if received > MODEL_BYTES:
                        raise RuntimeError('SCUNet download exceeds the expected model size.')
                    output.write(chunk)
                    if progress:
                        progress(f'SCUNet weights: {received/1e6:.1f} / {MODEL_BYTES/1e6:.1f} MB')
        if temporary.stat().st_size != MODEL_BYTES or _digest(temporary) != MODEL_SHA256:
            raise RuntimeError('SCUNet weights failed size/checksum verification; the previous file was retained.')
        os.replace(temporary, path)
        return path
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def install_commands(python, accelerator):
    """Matched official PyTorch wheels followed by the pinned optional loader."""
    if accelerator not in ('cpu', 'nvidia'):
        raise ValueError('Choose CPU or NVIDIA for SCUNet installation.')
    index = 'https://download.pytorch.org/whl/'+('cpu' if accelerator == 'cpu' else 'cu128')
    return [
        [str(python), '-m', 'pip', 'install', '--upgrade', 'torch>=2.6,<3', 'torchvision', '--index-url', index],
        [str(python), '-m', 'pip', 'install', SPANDREL_PACKAGE],
    ]


def _dependencies():
    try:
        import torch
        from spandrel import ImageModelDescriptor, ModelLoader
    except (ImportError, RuntimeError, OSError) as exc:
        raise RuntimeError('SCUNet needs optional PyTorch/Spandrel. Use SCUNet setup (CPU or NVIDIA GPU), then restart the app. Details: '+str(exc)) from exc
    return torch, ImageModelDescriptor, ModelLoader


def _load(device, progress):
    torch, descriptor_type, loader = _dependencies()
    if device == 'auto':
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
    if device not in ('cpu', 'cuda'):
        raise ValueError('SCUNet device must be auto, cpu or cuda.')
    if device == 'cuda' and not torch.cuda.is_available():
        raise RuntimeError('SCUNet CUDA was requested but this PyTorch/driver cannot use CUDA. No CPU fallback was performed.')
    path = ensure_weights(progress=progress)
    key = (str(path.resolve()), path.stat().st_mtime_ns, device)
    if key not in _MODELS:
        if progress:
            progress('SCUNet: loading real-PSNR model on '+device.upper())
        model = loader().load_from_file(str(path))
        if (not isinstance(model, descriptor_type) or model.architecture.id != 'SCUNet'
                or model.scale != 1 or model.input_channels != 3 or model.output_channels != 3):
            raise RuntimeError('The verified SCUNet weights did not load as a native-size RGB SCUNet model.')
        _MODELS.clear()
        _MODELS[key] = model.to(device=device, dtype=torch.float32).eval()
    return torch, _MODELS[key], device


def _starts(length, tile, step):
    positions = []
    for start in range(0, length, step):
        positions.append(start)
        if start+tile >= length:
            break
    return positions


def _axis_weight(length, start, end, total, overlap):
    weight = np.ones(length, np.float32)
    fade = np.sin((np.arange(overlap, dtype=np.float32)+.5)/overlap*np.pi/2)**2
    if start:
        weight[:min(length, overlap)] *= fade[:min(length, overlap)]
    if end < total:
        weight[-min(length, overlap):] *= fade[:min(length, overlap)][::-1]
    return weight


def tiled_inference(rgb, predict, tile=512, overlap=128, progress=None):
    """Blend overlapping predictions; all tile origins share the 64px phase.

    ``predict`` receives uint8 RGB and returns float RGB in [0,1]. Padding is
    reflected from the input, and removed after inference; there is no resizing.
    This geometry is independent of Torch so it can be tested without a model.
    """
    if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3 or min(rgb.shape[:2]) < 1:
        raise ValueError('SCUNet requires a nonempty uint8 RGB image.')
    if tile < 128 or tile % 64 or overlap < 64 or overlap % 64 or overlap >= tile:
        raise ValueError('SCUNet tiles/overlap must be multiples of 64, with 64 <= overlap < tile.')
    h, w = rgb.shape[:2]
    ph, pw = (-h) % 64, (-w) % 64
    padded = np.pad(rgb, ((0, ph), (0, pw), (0, 0)), mode='reflect' if min(h, w) > 1 else 'edge')
    height, width = padded.shape[:2]
    ys, xs = _starts(height, tile, tile-overlap), _starts(width, tile, tile-overlap)
    total = len(ys)*len(xs)
    accumulated = np.zeros(padded.shape, np.float32)
    weights = np.zeros(padded.shape[:2], np.float32)
    for row, top in enumerate(ys):
        bottom = min(height, top+tile)
        wy = _axis_weight(bottom-top, top, bottom, height, overlap)
        for column, left in enumerate(xs):
            right = min(width, left+tile)
            if progress:
                progress(f'SCUNet: tile {row*len(xs)+column+1} / {total}')
            predicted = np.asarray(predict(padded[top:bottom, left:right]), dtype=np.float32)
            if predicted.shape != (bottom-top, right-left, 3) or not np.isfinite(predicted).all():
                raise RuntimeError('SCUNet returned invalid RGB dimensions or nonfinite pixels.')
            wx = _axis_weight(right-left, left, right, width, overlap)
            weight = wy[:, None]*wx[None, :]
            accumulated[top:bottom, left:right] += np.clip(predicted, 0, 1)*weight[..., None]
            weights[top:bottom, left:right] += weight
    if np.any(weights <= 0):
        raise RuntimeError('SCUNet tile coverage is incomplete.')
    output = np.uint8(np.clip(accumulated[:h, :w]/weights[:h, :w, None]*255+.5, 0, 255))
    return output, {'tile_pixels': tile, 'overlap_pixels': overlap, 'tiles': total,
                    'padded_size': [width, height], 'native_size': [w, h],
                    'blend': 'raised-cosine overlap; 64-pixel-aligned origins; no resizing'}


def denoise(rgb, progress=None, *, device='auto', tile=512, overlap=128):
    """Return the complete learned-model output and its actual inference report."""
    if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3 or min(rgb.shape[:2]) < 1:
        raise ValueError('SCUNet requires a nonempty uint8 RGB image.')
    started = perf_counter()
    with _LOCK:
        torch, model, device = _load(device, progress)
        def predict(patch):
            tensor = torch.from_numpy(np.ascontiguousarray(patch.transpose(2, 0, 1))).float().unsqueeze(0)/255
            with torch.inference_mode():
                output = model(tensor.to(device))
            return output.detach().float().cpu().numpy()[0].transpose(1, 2, 0)
        attempted = []
        while True:
            attempted.append(tile)
            try:
                output, report = tiled_inference(rgb, predict, tile, overlap, progress)
                break
            except torch.cuda.OutOfMemoryError:
                if device != 'cuda' or tile <= 128:
                    raise RuntimeError('SCUNet ran out of GPU memory even with small tiles. No CPU/backend fallback was performed.') from None
                tile //= 2
                overlap = min(overlap, tile//2)
                torch.cuda.empty_cache()
                if progress:
                    progress(f'SCUNet: reducing tiles to {tile}px after GPU memory exhaustion')
        if device == 'cuda':
            torch.cuda.synchronize()
        report.update(model=MODEL_NAME, model_sha256=MODEL_SHA256, model_bytes=MODEL_BYTES,
                      device=device, device_name=torch.cuda.get_device_name() if device == 'cuda' else 'CPU',
                      torch_version=str(torch.__version__), precision='float32',
                      tiling_note='SCUNet can depend on wider context; overlap reduces seams but is not identical to whole-image inference.',
                      attempted_tile_pixels=attempted, model_only=True, seconds=perf_counter()-started)
    return output, report

