from io import BytesIO
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from stable_shift import scunet


@pytest.mark.parametrize('shape', [(1, 1), (1, 81), (45, 1), (17, 29), (129, 301), (513, 777)])
def test_tiling_preserves_native_rgb_dimensions_values_and_input_without_seams(shape):
    source = np.random.default_rng(21).integers(0, 256, (*shape, 3), dtype=np.uint8)
    copy = source.copy()
    sizes = []
    def predict(patch):
        sizes.append(patch.shape)
        return patch.astype(np.float32)/255
    result, report = scunet.tiled_inference(source, predict, tile=256, overlap=128)
    np.testing.assert_array_equal(result, copy)
    np.testing.assert_array_equal(source, copy)
    assert all(h % 64 == w % 64 == 0 for h, w, _ in sizes)
    assert report['native_size'] == [shape[1], shape[0]]
    assert report['tiles'] == len(sizes)


def test_tiling_does_not_restore_source_ink_or_attenuate_the_model_output():
    source = np.full((321, 609, 3), 255, np.uint8)
    source[80:200, 100:104] = (2, 50, 80)
    output, report = scunet.tiled_inference(source, lambda patch: np.zeros(patch.shape, np.float32), tile=256)
    assert not output.any()
    assert report['tiles'] > 1


@pytest.mark.parametrize('kwargs', [{'tile': 64}, {'tile': 300}, {'overlap': 0}, {'overlap': 512}])
def test_invalid_tiles_are_rejected(kwargs):
    with pytest.raises(ValueError, match='tiles/overlap'):
        scunet.tiled_inference(np.zeros((10, 10, 3), np.uint8), lambda a: a, **kwargs)


@pytest.mark.parametrize('bad', [lambda p: np.zeros((1, 1, 3)), lambda p: np.full(p.shape, np.nan)])
def test_bad_model_output_is_rejected(bad):
    with pytest.raises(RuntimeError, match='invalid RGB'):
        scunet.tiled_inference(np.zeros((50, 70, 3), np.uint8), bad)


def test_invalid_rgb_does_not_load_runtime_or_download_weights(monkeypatch):
    monkeypatch.setattr(scunet, '_load', lambda *a: pytest.fail('Runtime should not load'))
    with pytest.raises(ValueError, match='uint8 RGB'):
        scunet.denoise(np.zeros((20, 20, 4), np.uint8))


def _small_weights(monkeypatch):
    payload = b'official fixture model bytes'
    monkeypatch.setattr(scunet, 'MODEL_BYTES', len(payload))
    monkeypatch.setattr(scunet, 'MODEL_SHA256', sha256(payload).hexdigest())
    return payload


def test_download_is_verified_atomic_and_reused_without_network(tmp_path, monkeypatch):
    payload = _small_weights(monkeypatch)
    calls = []
    def fetch(request, timeout):
        calls.append(request.full_url)
        assert request.full_url == scunet.MODEL_URL
        return BytesIO(payload)
    monkeypatch.setattr(scunet, 'urlopen', fetch)
    target = tmp_path/scunet.MODEL_NAME
    assert scunet.ensure_weights(target) == target
    assert target.read_bytes() == payload
    assert scunet.ensure_weights(target) == target
    assert calls == [scunet.MODEL_URL]
    assert not list(tmp_path.glob('*.part'))


def test_bad_download_keeps_the_previous_file_and_removes_partial(tmp_path, monkeypatch):
    payload = _small_weights(monkeypatch)
    monkeypatch.setattr(scunet, 'urlopen', lambda *a, **k: BytesIO(b'x'*len(payload)))
    target = tmp_path/scunet.MODEL_NAME
    target.write_bytes(b'previous contents')
    with pytest.raises(RuntimeError, match='verification'):
        scunet.ensure_weights(target)
    assert target.read_bytes() == b'previous contents'
    assert not list(tmp_path.glob('*.part'))


def test_download_network_error_keeps_the_previous_file(tmp_path, monkeypatch):
    _small_weights(monkeypatch)
    def failed(*a, **k):
        raise OSError('offline')
    monkeypatch.setattr(scunet, 'urlopen', failed)
    target = tmp_path/scunet.MODEL_NAME
    target.write_bytes(b'old')
    with pytest.raises(OSError, match='offline'):
        scunet.ensure_weights(target)
    assert target.read_bytes() == b'old'
    assert not list(tmp_path.glob('*.part'))


@pytest.mark.parametrize('accelerator,suffix', [('cpu', '/cpu'), ('nvidia', '/cu128')])
def test_optional_installer_uses_matching_official_wheels(accelerator, suffix):
    commands = scunet.install_commands('/python with spaces/python.exe', accelerator)
    assert commands[0][0] == '/python with spaces/python.exe'
    assert commands[0][-1] == 'https://download.pytorch.org/whl'+suffix
    assert 'torchvision' in commands[0]
    assert commands[1][-1] == 'spandrel==0.4.2'


def test_missing_optional_runtime_is_actionable(monkeypatch):
    import builtins
    original = builtins.__import__
    def missing(name, *args, **kwargs):
        if name == 'torch':
            raise ImportError('not installed')
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', missing)
    with pytest.raises(RuntimeError, match='optional PyTorch/Spandrel'):
        scunet._dependencies()


def test_existing_app_and_cleanup_work_when_optional_modules_are_unavailable():
    import subprocess
    import sys
    code = '''
import sys, importlib.abc
class BlockOptional(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in ('torch', 'torchvision', 'spandrel'):
            raise ImportError('optional runtime deliberately unavailable')
sys.meta_path.insert(0, BlockOptional())
import stable_shift.app
from stable_shift.engine import Options, restore_quality
from PIL import Image
source=Image.new('RGB',(40,48),(90,110,130))
result,_=restore_quality(source,source,Options(method='Region cleanup only',color_match=False))
assert result.size==source.size
assert not any(name in sys.modules for name in ('torch','torchvision','spandrel'))
'''
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_pipeline_backend_retains_full_model_output_when_guards_and_cleanup_are_off(monkeypatch):
    from stable_shift.engine import Options, restore_quality
    source = np.full((64, 80, 3), (100, 125, 150), np.uint8)
    model = np.full_like(source, (80, 105, 130))
    calls = []
    def predict(rgb):
        calls.append(rgb.copy())
        return model.copy(), {'device': 'cpu', 'model_only': True}
    monkeypatch.setattr(scunet, 'denoise', predict)
    opts = Options(method='SCUNet', noise=100, color_noise=100, hard_guard=0, soft_guard=0,
                   source_guard=False, cleanup=0, blotch_strength=0, color_match=False)
    output, maps = restore_quality(Image.fromarray(source), Image.fromarray(source), opts)
    np.testing.assert_array_equal(output, model)
    assert len(calls) == 1
    np.testing.assert_array_equal(calls[0], source)
    assert maps['report']['scunet']['luminance_blend'] == 100
    assert '_scunet_report' not in maps


def test_zero_sliders_bypass_optional_runtime(monkeypatch):
    from stable_shift.engine import Options, restore_quality
    source = np.full((64, 80, 3), 100, np.uint8)
    monkeypatch.setattr(scunet, 'denoise', lambda *a: pytest.fail('Zero blend must bypass model'))
    output, maps = restore_quality(Image.fromarray(source), Image.fromarray(source), Options(
        method='SCUNet', noise=0, color_noise=0, source_guard=False, color_match=False))
    np.testing.assert_array_equal(output, source)
    assert maps['report']['scunet']['skipped']


def test_model_blend_endpoints_are_exact():
    source = np.full((5, 7, 3), 80, np.uint8)
    model = np.full_like(source, 160)
    np.testing.assert_array_equal(scunet.blend_strength(source, model, 0, 0), source)
    np.testing.assert_array_equal(scunet.blend_strength(source, model, 100, 100), model)
    np.testing.assert_array_equal(scunet.blend_strength(source, model, 50, 50), np.full_like(source, 120))


def test_auto_scunet_uses_blend_ceilings_and_source_spatial_limits_not_bm3d_sigmas():
    from stable_shift.engine import Options
    from stable_shift.automatic_strength import estimate_strength
    source = np.full((100, 120, 3), 160, np.uint8)
    rng = np.random.default_rng(44)
    source = np.uint8(np.clip(source.astype(float)+rng.normal(0, 5, source.shape), 0, 255))
    effective, maps, report = estimate_strength(source, Options(method='SCUNet', noise=80, color_noise=65))
    assert effective.noise == 80 and effective.color_noise == 65
    assert report['backend_sigma_lab'] is None
    assert not report['backend_skipped']
    assert np.any(maps['auto_denoise_luminance_strength'])
    assert 'not BM3D sigmas' in report['backend_strength_kind']


def test_auto_scunet_skips_quiet_constant_images_without_changing_other_methods():
    from stable_shift.engine import Options
    from stable_shift.automatic_strength import estimate_strength
    image = np.full((80, 100, 3), 150, np.uint8)
    _, _, report = estimate_strength(image, Options(method='SCUNet', noise=100, color_noise=100))
    assert report['backend_skipped']
    _, _, classical = estimate_strength(image, Options(method='CPU BM3D', noise=100, color_noise=100))
    assert 'backend_strength_kind' not in classical


def test_explicit_unavailable_cuda_does_not_load_weights_or_fall_back(monkeypatch):
    torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False))
    monkeypatch.setattr(scunet, '_dependencies', lambda: (torch, None, None))
    monkeypatch.setattr(scunet, 'ensure_weights', lambda **k: pytest.fail('Unavailable CUDA must fail before download'))
    with pytest.raises(RuntimeError, match='No CPU fallback'):
        scunet._load('cuda', None)


@pytest.mark.parametrize('succeed', [True, False])
def test_gpu_memory_retries_reduce_tiles_without_changing_backend(monkeypatch, succeed):
    class MemoryExhausted(RuntimeError):
        pass
    emptied, synchronized, attempts = [], [], []
    torch = SimpleNamespace(__version__='test', cuda=SimpleNamespace(
        OutOfMemoryError=MemoryExhausted, empty_cache=lambda: emptied.append(True),
        synchronize=lambda: synchronized.append(True), get_device_name=lambda: 'Test GPU'))
    monkeypatch.setattr(scunet, '_load', lambda *a: (torch, object(), 'cuda'))
    image = np.zeros((64, 64, 3), np.uint8)
    def tiled(rgb, predict, tile, overlap, progress):
        attempts.append((tile, overlap))
        if succeed and tile == 256:
            return rgb.copy(), {'tiles': 1}
        raise MemoryExhausted('out of memory')
    monkeypatch.setattr(scunet, 'tiled_inference', tiled)
    if succeed:
        output, report = scunet.denoise(image)
        np.testing.assert_array_equal(output, image)
        assert report['device'] == 'cuda'
        assert report['attempted_tile_pixels'] == [512, 256]
        assert attempts == [(512, 128), (256, 128)]
        assert len(emptied) == len(synchronized) == 1
    else:
        with pytest.raises(RuntimeError, match='No CPU/backend fallback'):
            scunet.denoise(image)
        assert attempts == [(512, 128), (256, 128), (128, 64)]
        assert len(emptied) == 2 and not synchronized
