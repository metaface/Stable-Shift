"""Focused always-on hook checks; generation/inference are simulated."""
import copy
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace as NS

import numpy as np
from PIL import Image
import pytest

from stable_shift import forge
from stable_shift.pipeline import Options


class Processed:
    def __init__(self, p, images_list, seed=-1, info='', subseed=None,
                 all_prompts=None, all_negative_prompts=None, all_seeds=None,
                 all_subseeds=None, index_of_first_image=0, infotexts=None, **kwargs):
        self.images, self.seed, self.info, self.subseed = images_list, seed, info, subseed
        self.all_prompts = all_prompts or p.all_prompts
        self.all_negative_prompts = all_negative_prompts or p.all_negative_prompts
        self.all_seeds = all_seeds or p.all_seeds
        self.all_subseeds = all_subseeds or p.all_subseeds
        self.index_of_first_image = index_of_first_image
        self.infotexts = infotexts or [info]*len(images_list)
        self.comments, self.extra_generation_params = '', p.extra_generation_params


@pytest.fixture
def host(monkeypatch, tmp_path):
    state = NS(interrupted=False, skipped=False, stopping_generation=False,
               job_count=7, job='external scheduler', job_timestamp='request-1', time_start=1.)
    state.interrupt = lambda: setattr(state, 'interrupted', True)
    state.assign_current_image = lambda image: setattr(state, 'current_image', image)
    opts = NS(img2img_color_correction=True, samples_save=True, return_grid=False,
              grid_save=False, grid_format='png')
    shared = ModuleType('modules.shared')
    shared.state, shared.opts = state, opts
    # QwenImage also sets this flag; it cannot be used to reject image models.
    shared.sd_model = NS(is_wan=True)
    p = NS(init_images=[Image.new('RGB', (64, 64), (50, 60, 70))],
           seed=123, subseed=45, prompt='drawing', negative_prompt='noise',
           batch_size=1, n_iter=1, color_corrections=None, denoising_strength=.5,
           inpainting_fill=0, image_mask=None, do_not_save_grid=False,
           do_not_save_samples=False, outpath_samples=str(tmp_path), outpath_grids=str(tmp_path),
           extra_generation_params={'Other extension': 'preserved'}, comments={}, script_args=[])
    p.comment = lambda message: p.comments.update({message: 1})
    result = NS(p=p, state=state, opts=opts, root=tmp_path, errors=[],
                inputs=[], references=[], raw_frames=[], saved=[], color_lists=[],
                settings=forge.Settings(enabled=True))

    def infotext(p, prompts, seeds, subseeds, *, index=0, all_negative_prompts=None):
        values = {key: value[index] if isinstance(value, list) else value
                  for key, value in p.extra_generation_params.items()}
        return prompts[index]+'\nSeed: '+str(seeds[index])+', '+', '.join(f'{k}: {v}' for k, v in values.items() if v is not None)

    def restore(reference, raw, options, progress, *, denoiser):
        progress('tile 1/1')
        result.references.append(reference.copy() if reference is not None else None)
        rgb = np.array(raw)
        rgb[..., 0] += 20
        return Image.fromarray(rgb), {'applied': {'denoise': float(raw.getpixel((0, 0))[0]),
            'deblotch': 85., 'color': 100. if reference is not None else 0.},
            'color_correction': {'requested_method': 'Robust global',
                                 'selected_method': 'Robust global' if reference is not None else 'Off'}}

    def process_images(p):
        cfg = result.settings
        result.inputs.append(p.init_images[0].copy() if getattr(p, 'init_images', None) else None)
        count = p.batch_size*p.n_iter
        p.all_prompts, p.all_negative_prompts = [p.prompt]*count, [p.negative_prompt]*count
        p.all_seeds, p.all_subseeds = [p.seed+i for i in range(count)], [p.subseed+i for i in range(count)]
        # Neo catches hook exceptions and continues; exercise that behavior.
        try:
            forge.begin(p, cfg)
        except Exception as exc:
            result.errors.append(str(exc))
        result.color_lists.append(p.color_corrections)
        outputs, texts = [], []
        if not state.interrupted:
            for index in range(count):
                raw = Image.new('RGB', (64, 64), (70+len(result.raw_frames), 80, 90))
                result.raw_frames.append(raw)
                pp = NS(image=raw, index=index)
                try:
                    forge.process_image(p, pp, cfg)
                except Exception as exc:
                    result.errors.append(str(exc))
                text = infotext(p, p.all_prompts, p.all_seeds, p.all_subseeds, index=index)
                if opts.samples_save and not p.do_not_save_samples:
                    result.saved.append((pp.image.copy(), text))
                outputs.append(pp.image)
                texts.append(text)
                if state.interrupted:
                    break
        p.color_corrections = None
        first = 0
        if opts.return_grid and not p.do_not_save_grid and len(outputs) > 1:
            outputs.insert(0, Image.new('RGB', (128, 64), 'magenta'))
            texts.insert(0, 'grid')
            first = 1
        proc = Processed(p, outputs, p.seed, texts[0] if texts else '', p.subseed,
                         infotexts=texts, index_of_first_image=first)
        forge.finish(p, proc, cfg)
        return proc

    modules = ModuleType('modules')
    modules.__path__ = []
    scripts = ModuleType('modules.scripts')
    scripts.Script = type('Script', (), {'elem_id': lambda self, name: name})
    scripts.AlwaysVisible = object()
    processing = ModuleType('modules.processing')
    processing.process_images, processing.Processed = process_images, Processed
    processing.create_infotext = infotext
    processing.fix_seed = lambda p: None
    images = ModuleType('modules.images')
    images.image_grid = lambda frames, **kwargs: Image.new('RGB', (128, 64), 'magenta')
    images.save_image = lambda *args, **kwargs: None
    modules.shared, modules.processing, modules.scripts, modules.images = shared, processing, scripts, images
    version = ModuleType('modules_forge.forge_version')
    version.version, version.release = 'neo', '2.33'
    for name, module in {'modules': modules, 'modules.shared': shared, 'modules.scripts': scripts,
        'modules.processing': processing, 'modules.images': images,
        'modules_forge': ModuleType('modules_forge'), 'modules_forge.forge_version': version}.items():
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(forge, 'restore', restore)
    result.process_images = process_images
    result.modules = modules
    return result


def test_disabled_panel_leaves_normal_generation_untouched(host):
    host.settings = forge.Settings(enabled=False)
    original = vars(host.p).copy()
    forge.setup(host.p, host.settings)
    proc = host.process_images(host.p)
    assert proc.images[0].tobytes() == host.raw_frames[0].tobytes()
    assert not host.references and not list(host.root.iterdir())
    assert host.p.extra_generation_params == original['extra_generation_params']
    assert host.p.init_images is original['init_images'] and host.p.seed == original['seed']
    assert host.state.job_count == 7 and host.state.job == 'external scheduler'


def test_txt2img_needs_no_reference_and_accepts_wan_vae_image_models(host):
    host.p.init_images = None
    host.settings = forge.Settings(True, Options(reference=False), 'Off')
    forge.setup(host.p, host.settings)
    proc = host.process_images(host.p)
    assert not host.errors and host.references == [None]
    assert proc.images[0].getpixel((0, 0)) == (90, 80, 90)
    assert 'Stable Shift color method: Off' in proc.infotexts[0]
    assert host.state.job_count == 7 and host.p.seed == 123


def test_shallow_copies_keep_fixed_anchor_and_batch_metadata_before_saving(host):
    host.p.batch_size = 2
    host.opts.return_grid = True
    initial = host.p.init_images[0].copy()
    native_color = [object()]
    host.p.color_corrections = native_color
    forge.setup(host.p, host.settings)
    previous = None
    for _ in range(2):
        copied = copy.copy(host.p)
        if previous is not None:
            copied.init_images = [previous.copy()]
        proc = host.process_images(copied)
        assert proc.index_of_first_image == 1 and len(proc.images) == 3
        assert copied.color_corrections is native_color
        assert 'Other extension: preserved' in proc.infotexts[1]
        assert proc.infotexts[1] != proc.infotexts[2]
        previous = proc.images[1]
    assert all(ref.tobytes() == initial.tobytes() for ref in host.references)
    assert all(value == [] for value in host.color_lists)
    assert host.p.init_images[0].tobytes() == initial.tobytes()
    assert host.p.extra_generation_params == {'Other extension': 'preserved'}
    assert host.inputs[1].tobytes() == host.saved[0][0].tobytes()
    directory, = (host.root/'stable-shift').iterdir()
    journal = json.loads((directory/'report.json').read_text())
    assert len(journal['frames']) == len(host.references) == 4
    assert journal['frames'][2]['handoff']['generation_input_signature'] == journal['frames'][0]['handoff']['feedback_signature']
    with Image.open(directory/'0002-restored.png') as saved:
        assert saved.tobytes() == host.saved[1][0].tobytes()
        assert 'Seed: 124' in saved.info['parameters'] and 'Stable Shift frame: 2' in saved.info['parameters']


def test_uploaded_reference_and_next_request_use_their_own_anchor(host):
    reference = Image.new('RGB', (64, 64), (11, 22, 33))
    host.settings = forge.Settings(True, reference_mode='Uploaded reference', reference_image=reference)
    forge.setup(host.p, host.settings)
    host.process_images(host.p)
    assert host.references[-1].tobytes() == reference.tobytes()
    host.state.time_start = 2.
    host.p.init_images = [Image.new('RGB', (64, 64), (99, 98, 97))]
    host.settings = forge.Settings(True)
    host.process_images(host.p)
    assert host.references[-1].tobytes() == host.p.init_images[0].tobytes()
    assert len(list((host.root/'stable-shift').iterdir())) == 2


def test_hook_failure_stops_feedback_even_when_neo_swallows_exception(host, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError('SCUNet failed')
    monkeypatch.setattr(forge, 'restore', fail)
    forge.setup(host.p, host.settings)
    proc = host.process_images(host.p)
    assert host.state.interrupted and not proc.images
    assert host.errors == ['SCUNet failed']
    assert 'SCUNet failed' in proc.info
    assert 'Stable Shift status: Failed' in host.saved[0][1]
    directory, = (host.root/'stable-shift').iterdir()
    assert json.loads((directory/'report.json').read_text())['status'] == 'failed'


def test_stop_after_current_batch_finishes_restoration(host):
    host.state.stopping_generation = True
    forge.setup(host.p, host.settings)
    proc = host.process_images(host.p)
    assert len(proc.images) == 1 and proc.images[0].getpixel((0, 0))[0] == 90
    assert not host.state.interrupted


@pytest.mark.parametrize('fails', [False, True])
def test_gpu_handoff_releases_scunet_even_on_failure(monkeypatch, fails):
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
    monkeypatch.setattr(forge.scunet, 'denoise', denoise)
    monkeypatch.setattr(forge.scunet, 'clear_cache', lambda: events.append('release SCUNet'))
    if fails:
        with pytest.raises(RuntimeError, match='GPU error'):
            forge._forge_denoise(None, None)
    else:
        forge._forge_denoise(None, None)
    assert events == ['offload Forge', 'empty allocator', 'SCUNet', 'release SCUNet', 'empty allocator']
