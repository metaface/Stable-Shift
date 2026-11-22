"""Forge Neo 2.33 adapter: generation -> restoration -> next init image.

Forge imports stay inside the entry points so the processing core remains
usable without loading the WebUI, Gradio, or Tk.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

from PIL import ImageOps

from . import __version__, FORGE_TEST_VERSION
from .global_color import color_method_label
from .pipeline import Options, restore
from .preview import image_signature
from . import scunet

REFERENCE_MODES = ('Starting image', 'Uploaded reference', 'Off')
SEED_MODES = ('Increment', 'Fixed')


class RestorationInterrupted(Exception):
    """A user interruption, never a request to feed an unrestored frame back."""


def _forge_denoise(rgb, progress):
    from backend import memory_management as memory

    device = memory.get_torch_device().type
    if device not in ('cuda', 'cpu'):
        raise RuntimeError('This first Stable Shift test supports Forge CUDA or CPU inference.')
    try:
        if device == 'cuda':
            memory.unload_all_models()
            memory.soft_empty_cache()
        return scunet.denoise(rgb, progress, device=device)
    finally:
        scunet.clear_cache()
        if device == 'cuda':
            memory.soft_empty_cache()


def _write_report(directory, report):
    if directory is not None:
        temporary = directory/'report.json.tmp'
        temporary.write_text(json.dumps(report, indent=2), encoding='utf-8')
        temporary.replace(directory/'report.json')


def _validate(p, loops, seed_mode, reference_mode, reference_image, options):
    if isinstance(loops, bool) or not 1 <= float(loops) <= 32 or int(loops) != float(loops):
        raise ValueError('Stable Shift loops must be a whole number from 1 to 32.')
    if seed_mode not in SEED_MODES or reference_mode not in REFERENCE_MODES:
        raise ValueError('Unknown Stable Shift seed/reference mode.')
    if not p.init_images or len(p.init_images) != 1:
        raise ValueError('Use one starting image for Stable Shift Loopback.')
    if p.batch_size != 1 or p.n_iter != 1:
        raise ValueError('Set Forge Batch size and Batch count to 1; use Stable Shift Loops for iterations.')
    if getattr(p, 'image_mask', None) is not None or getattr(p, 'mask', None) is not None:
        raise ValueError('This first Stable Shift test uses ordinary img2img, without an inpainting mask.')
    if any(isinstance(getattr(p, name), list) for name in ('prompt', 'negative_prompt', 'seed', 'subseed')):
        raise ValueError('This first Stable Shift test uses one prompt and one seed, without prompt/seed lists.')
    if reference_mode == 'Uploaded reference' and reference_image is None:
        raise ValueError('Upload a color reference or choose Starting image / Off.')
    options.validate()


def run(p, loops=3, seed_mode='Increment', reference_mode='Starting image',
        reference_image=None, options=Options(), save_test=True):
    """Run a single chain; every completed gallery frame is restored feedback."""
    from modules import images, processing, shared
    from modules_forge.forge_version import release, version

    _validate(p, loops, seed_mode, reference_mode, reference_image, options)
    try:
        host_version = tuple(int(part) for part in release.split('.'))
    except ValueError:
        host_version = ()
    if version != 'neo' or host_version < (2, 33):
        raise RuntimeError('Stable Shift targets Forge Neo 2.33. Update Forge Neo before running this test.')
    if getattr(shared.sd_model, 'is_wan', False):
        raise ValueError('This first Stable Shift test supports still-image img2img models.')

    loops = int(loops)
    state, opts = shared.state, shared.opts
    source = ImageOps.exif_transpose(p.init_images[0]).convert('RGB').copy()
    reference = (source.copy() if reference_mode == 'Starting image' else
                 ImageOps.exif_transpose(reference_image).convert('RGB').copy()
                 if reference_mode == 'Uploaded reference' else None)
    directory = None
    journal = {'extension': 'Stable Shift', 'core_version': __version__,
               'forge_test_version': FORGE_TEST_VERSION, 'forge_version': f'{version}-{release}',
               'requested_loops': loops, 'seed_mode': seed_mode, 'reference_mode': reference_mode,
               'reference_signature': image_signature(reference) if reference else None,
               'status': 'running', 'loops': []}
    if save_test:
        stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        directory = Path(p.outpath_samples)/'stable-shift'/f'{stamp}_{uuid4().hex[:8]}'
        directory.mkdir(parents=True, exist_ok=False)
        source.save(directory/'00-input.png')
        if reference is not None:
            reference.save(directory/'00-color-reference.png')
        _write_report(directory, journal)
        print(f'[Stable Shift] Comparison files: {directory}')

    owned = ('init_images', 'seed', 'subseed', 'color_corrections',
             'do_not_save_samples', 'do_not_save_grid', 'extra_generation_params')
    original = {name: getattr(p, name) for name in owned}
    auto_save = opts.samples_save and not p.do_not_save_samples
    frames, texts, seeds, subseeds, prompts, negatives = [], [], [], [], [], []
    last_params = dict(p.extra_generation_params or {})

    def progress(message):
        if state.interrupted or state.skipped:
            raise RestorationInterrupted()
        state.job = f'Stable Shift {len(frames)+1}/{loops}: {message}'
        state.textinfo = state.job

    try:
        processing.fix_seed(p)
        first_seed = p.seed
        p.do_not_save_grid = p.do_not_save_samples = True
        p.extra_generation_params = dict(p.extra_generation_params or {})
        p.extra_generation_params.update({
            'Stable Shift': f'{__version__} / Neo test {FORGE_TEST_VERSION}',
            'Stable Shift loops': loops, 'Stable Shift seed mode': seed_mode,
            'Stable Shift reference': reference_mode,
        })
        p.init_images = [source.copy()]
        state.job_count = loops
        try:
            for index in range(loops):
                if state.interrupted or state.skipped or state.stopping_generation:
                    break
                progress('generating')
                p.extra_generation_params['Stable Shift loop'] = index+1
                # An empty list suppresses Neo's automatic histogram correction
                # without touching the global option. Neo clears it after each pass.
                p.color_corrections = []
                feedback_input = image_signature(p.init_images[0])
                generated = processing.process_images(p)
                progress('restoring')
                first = generated.index_of_first_image
                if first >= len(generated.images):
                    raise RuntimeError('Forge returned no generated image to restore.')
                raw = generated.images[first].convert('RGB')
                cleaned, report = restore(reference, raw, options, progress, denoiser=_forge_denoise)
                progress('finishing restoration')
                if cleaned.size != raw.size:
                    raise RuntimeError('Stable Shift restoration must retain the generated image dimensions.')
                actual = report['applied']
                actual_method = color_method_label(report['color_correction']) if actual['color'] else 'Off'
                params = {'Stable Shift automatic': options.automatic,
                          'Stable Shift denoise': actual['denoise'],
                          'Stable Shift deblotch': actual['deblotch'],
                          'Stable Shift color': actual['color'],
                          'Stable Shift color method': actual_method}
                p.extra_generation_params.update(params)
                text = generated.infotexts[first] if first < len(generated.infotexts) else generated.info
                text += ', '+', '.join(f'{key}: {value}' for key, value in params.items())
                cleaned.info['parameters'] = text
                seed, subseed = int(generated.seed), int(generated.subseed)
                prompt, negative = generated.all_prompts[0], generated.all_negative_prompts[0]
                report['loopback'] = {'loop': index+1, 'seed': seed, 'subseed': subseed,
                                      'generation_input_signature': feedback_input,
                                      'feedback_signature': image_signature(cleaned)}
                if auto_save:
                    images.save_image(cleaned, p.outpath_samples, '', seed, prompt,
                                      opts.samples_format, info=text, p=p,
                                      suffix=f'-stable-shift-{index+1:03d}')
                if directory is not None:
                    raw.save(directory/f'{index+1:02d}-generated.png')
                    images.save_image(cleaned, str(directory), '', seed, prompt, 'png',
                                      info=text, p=p, forced_filename=f'{index+1:02d}-restored',
                                      save_to_dirs=False)
                journal['loops'].append(report)
                _write_report(directory, journal)
                frames.append(cleaned)
                texts.append(text)
                seeds.append(seed)
                subseeds.append(subseed)
                prompts.append(prompt)
                negatives.append(negative)
                last_params = dict(p.extra_generation_params)
                state.assign_current_image(cleaned)
                print(f'[Stable Shift] Loop {index+1}/{loops}: denoise {actual["denoise"]:g}%, '
                      f'deblotch {actual["deblotch"]:g}%, color {actual["color"]:g}% ({actual_method})')
                # PIL feedback stays lossless, even if normal samples are saved as JPEG.
                p.init_images = [cleaned.copy()]
                p.seed = (seed+1) % 4294967294 if seed_mode == 'Increment' else first_seed
                # Per-loop strengths belong only to that restored frame's metadata.
                for key in params:
                    p.extra_generation_params.pop(key, None)
        except RestorationInterrupted:
            pass

        journal['status'] = 'completed' if len(frames) == loops else 'stopped'
        result = processing.Processed(p, frames, seed=seeds[0] if seeds else p.seed,
            info=texts[0] if texts else 'Stable Shift stopped before a restored frame was completed.',
            subseed=subseeds[0] if subseeds else p.subseed, all_seeds=seeds, all_subseeds=subseeds,
            all_prompts=prompts, all_negative_prompts=negatives, infotexts=texts)
        result.extra_generation_params = last_params
        if directory is not None:
            result.comments += f'\nStable Shift comparison files: {directory}'
        return result
    except Exception as exc:
        journal.update(status='failed', error=str(exc))
        raise
    finally:
        for name, value in original.items():
            setattr(p, name, value)
        _write_report(directory, journal)
