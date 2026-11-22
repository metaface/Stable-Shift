"""Focused adapter tests; no diffusion checkpoint or SCUNet inference required."""
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace as NS

import numpy as np
from PIL import Image, PngImagePlugin
import pytest

from stable_shift import forge_loopback as adapter
from stable_shift.pipeline import Options


class Processed:
    # Neo 2.33 constructor contract; only the fields needed by this adapter.
    def __init__(self, p, images_list, seed=-1, info='', subseed=None,
                 all_prompts=None, all_negative_prompts=None, all_seeds=None,
                 all_subseeds=None, index_of_first_image=0, infotexts=None,
                 comments='', extra_images_list=None):
        self.images, self.seed, self.info, self.subseed = images_list, seed, info, subseed
        self.all_prompts = all_prompts or [p.prompt]
        self.all_negative_prompts = all_negative_prompts or [p.negative_prompt]
        self.all_seeds, self.all_subseeds = all_seeds or [seed], all_subseeds or [subseed]
        self.index_of_first_image = index_of_first_image
        self.infotexts = infotexts or [info]*len(images_list)
        self.comments, self.extra_generation_params = '', p.extra_generation_params


@pytest.fixture
def host(monkeypatch, tmp_path):
    state = NS(interrupted=False, skipped=False, stopping_generation=False,
               job_count=0, job='', textinfo=None, current_image=None)
    state.assign_current_image = lambda image: setattr(state, 'current_image', image)
    opts = NS(samples_save=True, samples_format='png', img2img_color_correction=True)
    shared = NS(state=state, opts=opts, sd_model=NS(is_wan=False))
    generated_inputs, restored_refs, saved = [], [], []
    p = NS(init_images=[Image.new('RGB', (64, 64), (50, 60, 70))], seed=123, subseed=45,
           prompt='a drawing', negative_prompt='noise', batch_size=1, n_iter=1,
           color_corrections=None, do_not_save_samples=False, do_not_save_grid=False,
           extra_generation_params={'Another extension': 'kept'}, outpath_samples=str(tmp_path),
           image_mask=None, mask=None)

    def generate(p):
        assert p.do_not_save_samples and p.do_not_save_grid
        assert p.color_corrections == [] and opts.img2img_color_correction is True
        generated_inputs.append((p.init_images[0].copy(), p.seed))
        raw = Image.new('RGB', (64, 64), (80+len(generated_inputs), 90, 100))
        # Ensure a returned grid cannot become feedback.
        result = Processed(p, [Image.new('RGB', (128, 64), 'red'), raw], seed=p.seed,
            subseed=p.subseed, info='grid', index_of_first_image=1,
            infotexts=['grid', f'{p.prompt}\nSteps: 20, Seed: {p.seed}'])
        p.color_corrections = None  # Neo resets this after every generation.
        return result

    def restore(reference, raw, options, progress, *, denoiser):
        assert denoiser is adapter._forge_denoise
        progress('tile 1/1')
        restored_refs.append(reference.copy() if reference else None)
        pixels = np.array(raw)
        pixels[..., 0] += 20
        return Image.fromarray(pixels), {
            'applied': {'denoise': 100., 'deblotch': 85., 'color': 100.},
            'color_correction': {'selected_method': 'Robust global', 'requested_method': 'Robust global'}}

    def save(image, path, basename, seed, prompt, extension, *, info, p, suffix='',
             forced_filename=None, save_to_dirs=None):
        name = forced_filename or f'sample-{seed}{suffix}'
        target = Path(path)/(name+'.'+extension)
        target.parent.mkdir(parents=True, exist_ok=True)
        pnginfo = PngImagePlugin.PngInfo()
        pnginfo.add_text('parameters', info)
        image.save(target, pnginfo=pnginfo)
        saved.append((target, image.copy(), info))

    modules = ModuleType('modules')
    modules.shared = shared
    modules.processing = NS(process_images=generate, Processed=Processed, fix_seed=lambda p: None)
    modules.images = NS(save_image=save)
    forge = ModuleType('modules_forge')
    version = ModuleType('modules_forge.forge_version')
    version.release, version.version = '2.33', 'neo'
    monkeypatch.setitem(sys.modules, 'modules', modules)
    monkeypatch.setitem(sys.modules, 'modules_forge', forge)
    monkeypatch.setitem(sys.modules, 'modules_forge.forge_version', version)
    monkeypatch.setattr(adapter, 'restore', restore)
    return NS(p=p, modules=modules, state=state, inputs=generated_inputs,
              references=restored_refs, saved=saved, root=tmp_path)


@pytest.mark.parametrize('seed_mode,expected', [('Increment', [123, 124, 125]), ('Fixed', [123]*3)])
def test_restored_feedback_fixed_reference_and_saved_metadata(host, seed_mode, expected):
    original = vars(host.p).copy()
    result = adapter.run(host.p, loops=3, seed_mode=seed_mode)
    assert [seed for _, seed in host.inputs] == result.all_seeds == expected
    assert len(result.images) == len(result.infotexts) == 3
    assert all(ref.tobytes() == original['init_images'][0].tobytes() for ref in host.references)
    for index in (1, 2):
        assert host.inputs[index][0].tobytes() == result.images[index-1].tobytes()
    assert all(image.size == (64, 64) for image in result.images)
    assert vars(host.p) == original
    assert result.extra_generation_params['Another extension'] == 'kept'
    assert result.extra_generation_params['Stable Shift deblotch'] == 85
    directory, = (host.root/'stable-shift').iterdir()
    report = json.loads((directory/'report.json').read_text())
    assert report['status'] == 'completed' and len(report['loops']) == 3
    for index, loop in enumerate(report['loops']):
        with Image.open(directory/f'{index+1:02d}-restored.png') as saved:
            assert saved.tobytes() == result.images[index].tobytes()
            assert f'Seed: {expected[index]}' in saved.info['parameters']
            assert 'Stable Shift deblotch: 85.0' in saved.info['parameters']
        if index:
            assert loop['loopback']['generation_input_signature'] == report['loops'][index-1]['loopback']['feedback_signature']


def test_interrupt_during_restoration_returns_only_completed_feedback(host, monkeypatch):
    normal = adapter.restore
    def interrupted(*args, **kwargs):
        if len(host.inputs) == 2:
            host.state.interrupted = True
            args[3]('tile 2/4')
        return normal(*args, **kwargs)
    monkeypatch.setattr(adapter, 'restore', interrupted)
    result = adapter.run(host.p, loops=3)
    assert len(host.inputs) == 2 and len(result.images) == 1
    directory, = (host.root/'stable-shift').iterdir()
    assert json.loads((directory/'report.json').read_text())['status'] == 'stopped'
    assert not (directory/'02-restored.png').exists()
    assert host.p.do_not_save_samples is False and host.p.seed == 123


def test_stop_after_batch_finishes_current_restoration(host):
    generate = host.modules.processing.process_images
    def stop_after_generation(p):
        result = generate(p)
        host.state.stopping_generation = True
        return result
    host.modules.processing.process_images = stop_after_generation
    result = adapter.run(host.p, loops=3, save_test=False)
    assert len(host.inputs) == len(result.images) == 1
    assert result.images[0].getpixel((0, 0))[0] == 101


def test_manual_zero_strengths_and_no_reference_keep_pixels_without_files(host, monkeypatch):
    from stable_shift.pipeline import restore
    monkeypatch.setattr(adapter, 'restore', restore)
    host.modules.shared.opts.samples_save = False
    result = adapter.run(host.p, loops=1, reference_mode='Off', save_test=False,
        options=Options(automatic=False, denoise=0, deblotch=0, color=0, reference=False))
    assert result.images[0].getpixel((0, 0)) == (81, 90, 100)
    assert not list(host.root.iterdir()) and not host.saved
    assert result.extra_generation_params['Stable Shift color method'] == 'Off'


def test_restoration_failure_stops_chain_and_restores_host(host, monkeypatch):
    original = vars(host.p).copy()
    def fail(*args, **kwargs):
        raise RuntimeError('SCUNet failed')
    monkeypatch.setattr(adapter, 'restore', fail)
    with pytest.raises(RuntimeError, match='SCUNet failed'):
        adapter.run(host.p, loops=3)
    assert len(host.inputs) == 1 and vars(host.p) == original
    directory, = (host.root/'stable-shift').iterdir()
    report = json.loads((directory/'report.json').read_text())
    assert report['status'] == 'failed' and report['loops'] == []


@pytest.mark.parametrize('fails', [False, True])
def test_scunet_gpu_handoff_releases_model_even_on_failure(monkeypatch, fails):
    events = []
    backend = ModuleType('backend')
    backend.memory_management = NS(get_torch_device=lambda: NS(type='cuda'),
        unload_all_models=lambda: events.append('offload Forge'),
        soft_empty_cache=lambda: events.append('empty allocator'))
    monkeypatch.setitem(sys.modules, 'backend', backend)
    def denoise(rgb, progress, *, device):
        assert device == 'cuda'
        events.append('SCUNet')
        if fails:
            raise RuntimeError('GPU error')
        return rgb, {}
    monkeypatch.setattr(adapter.scunet, 'denoise', denoise)
    monkeypatch.setattr(adapter.scunet, 'clear_cache', lambda: events.append('release SCUNet'))
    if fails:
        with pytest.raises(RuntimeError, match='GPU error'):
            adapter._forge_denoise(None, None)
    else:
        adapter._forge_denoise(None, None)
    assert events == ['offload Forge', 'empty allocator', 'SCUNet', 'release SCUNet', 'empty allocator']


@pytest.mark.parametrize('changes', [{'batch_size': 2}, {'n_iter': 2}, {'image_mask': object()}])
def test_unsupported_input_is_rejected_before_generating(host, changes):
    vars(host.p).update(changes)
    with pytest.raises(ValueError):
        adapter.run(host.p)
    assert not host.inputs and not host.saved


def test_pipeline_injected_inference_keeps_native_pixels_at_zero_cleanup():
    from stable_shift.pipeline import restore
    rgb = np.random.default_rng(3).integers(0, 256, (64, 64, 3), dtype=np.uint8)
    expected = np.full_like(rgb, [70, 100, 130])
    calls = []
    def denoiser(source, progress):
        calls.append(source.copy())
        return expected.copy(), {'device': 'test'}
    result, report = restore(None, Image.fromarray(rgb),
        Options(automatic=False, denoise=100, deblotch=0, color=0, reference=False),
        denoiser=denoiser)
    assert len(calls) == 1 and np.array_equal(calls[0], rgb)
    assert np.array_equal(np.array(result), expected) and report['applied']['denoise'] == 100
