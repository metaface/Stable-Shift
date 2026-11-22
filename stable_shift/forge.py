"""Restore native image outputs before Forge saves or returns them.

Request state lives on the processing object. Selectable scripts can shallow-copy
that object and still share the original color anchor and comparison session.
This module never schedules generations or chooses their prompts, inputs or seeds.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps, PngImagePlugin

from . import __version__, FORGE_TEST_VERSION
from .global_color import color_method_label
from .pipeline import Options, restore
from .preview import image_signature
from . import scunet

REFERENCE_MODES = ('Starting image', 'Uploaded reference', 'Off')
SESSION = '_stable_shift_session'
PASS = '_stable_shift_pass'
PREFIX = 'Stable Shift'


@dataclass(frozen=True)
class Settings:
    enabled: bool = False
    options: Options = Options()
    reference_mode: str = 'Starting image'
    reference_image: object = None
    save_test: bool = True


@dataclass
class Session:
    settings: Settings
    token: tuple
    source: object = None
    reference: object = None
    initialized: bool = False
    directory: object = None
    failed: bool = False
    count: int = 0
    report: dict = field(default_factory=dict)


@dataclass
class Pass:
    session: Session
    input_signature: object
    color_corrections: object
    owns_color: bool
    restored: dict = field(default_factory=dict)
    failed: bool = False


class RestorationInterrupted(Exception):
    pass


def _token():
    from modules import shared
    return (shared.state.job_timestamp, shared.state.time_start)


def _input(p):
    images = getattr(p, 'init_images', None)
    return images[0] if images and isinstance(images[0], Image.Image) else None


def _rgb(image):
    return ImageOps.exif_transpose(image).convert('RGB').copy()


def _new_session(p, settings):
    settings.options.validate()
    if settings.reference_mode not in REFERENCE_MODES:
        raise ValueError('Unknown Stable Shift color reference mode.')
    if settings.reference_mode == 'Uploaded reference' and not isinstance(settings.reference_image, Image.Image):
        raise ValueError('Upload a Stable Shift color reference or choose Starting image / Off.')
    source = _input(p)
    session = Session(settings, _token(), source=_rgb(source) if source is not None else None)
    if settings.reference_mode == 'Uploaded reference':
        session.reference = _rgb(settings.reference_image)
    setattr(p, SESSION, session)
    return session


def _write_report(session):
    if session.directory is not None:
        temporary = session.directory/'report.json.tmp'
        temporary.write_text(json.dumps(session.report, indent=2), encoding='utf-8')
        temporary.replace(session.directory/'report.json')


def _initialize(p, session):
    if session.initialized:
        return
    settings = session.settings
    if session.source is None and _input(p) is not None:
        session.source = _rgb(_input(p))
    if settings.reference_mode == 'Starting image' and session.source is not None:
        session.reference = session.source.copy()
    from modules_forge.forge_version import release, version
    session.report = {'extension': PREFIX, 'core_version': __version__,
        'forge_test_version': FORGE_TEST_VERSION, 'forge_version': f'{version}-{release}',
        'reference_mode': settings.reference_mode,
        'reference_signature': image_signature(session.reference) if session.reference is not None else None,
        'status': 'running', 'frames': []}
    if settings.reference_mode == 'Starting image' and session.reference is None:
        session.report['reference_note'] = 'No starting image; color correction is disabled. An uploaded reference can be used with txt2img.'
    if settings.save_test:
        stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        session.directory = Path(p.outpath_samples)/'stable-shift'/f'{stamp}_{uuid4().hex[:8]}'
        session.directory.mkdir(parents=True, exist_ok=False)
        if session.source is not None:
            session.source.save(session.directory/'00-input.png')
        if session.reference is not None:
            session.reference.save(session.directory/'00-color-reference.png')
        print(f'[Stable Shift] Comparison files: {session.directory}')
    session.initialized = True
    _write_report(session)


def _fail(p, message, status='failed'):
    from modules import shared
    # Neo logs and catches ordinary hook exceptions. Set its interruption flag
    # explicitly so a selectable script cannot start another generation.
    shared.state.interrupt()
    shared.state.textinfo = f'Stable Shift {status}: {message}'
    p.comment(shared.state.textinfo)
    session = getattr(p, SESSION, None)
    if session is not None:
        session.failed = True
        session.report.update(status=status, error=str(message))
        _write_report(session)
    current = getattr(p, PASS, None)
    if current is not None:
        current.failed = True


def setup(p, settings):
    """Capture the original anchor before Loopback changes or copies p."""
    setattr(p, PASS, None)
    if not settings.enabled:
        setattr(p, SESSION, None)
        return
    try:
        _new_session(p, settings)
    except Exception as exc:
        _fail(p, str(exc))
        raise


def begin(p, settings):
    """Called for each process_images pass, including each external loop."""
    if not settings.enabled:
        return
    try:
        session = getattr(p, SESSION, None)
        if session is None or session.token != _token():
            session = _new_session(p, settings)
        if session.failed:
            raise RuntimeError('Stable Shift stopped this request after a restoration error or interruption.')
        _initialize(p, session)
        options = session.settings.options
        owns_color = session.reference is not None and options.reference and (options.automatic or options.color > 0)
        source = _input(p)
        current = Pass(session, image_signature(source) if source is not None else None,
                       getattr(p, 'color_corrections', None), owns_color)
        setattr(p, PASS, current)
        # Copy metadata because third-party scripts can shallow-copy p.
        p.extra_generation_params = {k: v for k, v in (p.extra_generation_params or {}).items()
                                     if not k.startswith(PREFIX)}
        p.extra_generation_params.update({
            PREFIX: f'{__version__} / Neo test {FORGE_TEST_VERSION}',
            PREFIX+' enabled': True, PREFIX+' automatic': options.automatic,
            PREFIX+' reference': settings.reference_mode,
            PREFIX+' requested color method': options.color_method,
            PREFIX+' requested denoise': options.denoise,
            PREFIX+' requested deblotch': options.deblotch,
            PREFIX+' requested color': options.color,
        })
        if owns_color:
            # The host's img2img init checks for None before constructing its
            # histogram correction. This also overrides native Loopback's list.
            p.color_corrections = []
        session.report['status'] = 'running'
    except Exception as exc:
        _fail(p, str(exc))
        raise


def _forge_denoise(rgb, progress):
    from backend import memory_management as memory
    device = memory.get_torch_device().type
    if device not in ('cuda', 'cpu'):
        raise RuntimeError('Stable Shift currently supports Forge CUDA or CPU inference.')
    try:
        if device == 'cuda':
            memory.unload_all_models()
            memory.soft_empty_cache()
        return scunet.denoise(rgb, progress, device=device)
    finally:
        scunet.clear_cache()
        if device == 'cuda':
            memory.soft_empty_cache()


def _metadata(p, index, values):
    total = max(index+1, len(p.all_seeds))
    for key, value in values.items():
        key = PREFIX+' '+key
        items = p.extra_generation_params.setdefault(key, [None]*total)
        items.extend([None]*max(0, total-len(items)))
        items[index] = value


def process_image(p, pp, settings):
    """After compositing, before native saving, gallery and script feedback."""
    current = getattr(p, PASS, None)
    if not settings.enabled or current is None or current.failed:
        return
    if pp.index in current.restored:
        pp.image = current.restored[pp.index]
        return
    from modules import processing, shared
    session = current.session
    session.count += 1
    frame = session.count
    options = session.settings.options

    def progress(message):
        if shared.state.interrupted or shared.state.skipped:
            raise RestorationInterrupted()
        shared.state.textinfo = f'Stable Shift image {frame}: {message}'

    try:
        progress('restoring')
        raw = pp.image.convert('RGB')
        if session.directory is not None:
            raw.save(session.directory/f'{frame:04d}-generated.png')
        cleaned, report = restore(session.reference, raw, options, progress, denoiser=_forge_denoise)
        progress('finishing restoration')
        if cleaned.size != raw.size:
            raise RuntimeError('Stable Shift must retain the generated image dimensions.')
        applied = report['applied']
        method = color_method_label(report['color_correction']) if applied['color'] else 'Off'
        _metadata(p, pp.index, {'status': 'Completed', 'frame': frame,
            'denoise': applied['denoise'], 'deblotch': applied['deblotch'],
            'color': applied['color'], 'color method': method})
        text = processing.create_infotext(p, p.all_prompts, p.all_seeds, p.all_subseeds,
                                         index=pp.index, all_negative_prompts=p.all_negative_prompts)
        cleaned.info['parameters'] = text
        report['handoff'] = {'frame': frame, 'sample_index': pp.index,
            'seed': p.all_seeds[pp.index], 'subseed': p.all_subseeds[pp.index],
            'generation_input_signature': current.input_signature,
            'feedback_signature': image_signature(cleaned)}
        if session.directory is not None:
            pnginfo = PngImagePlugin.PngInfo()
            pnginfo.add_text('parameters', text)
            cleaned.save(session.directory/f'{frame:04d}-restored.png', pnginfo=pnginfo)
        session.report['frames'].append(report)
        _write_report(session)
        pp.image = cleaned
        current.restored[pp.index] = cleaned
        shared.state.assign_current_image(cleaned)
        print(f'[Stable Shift] Image {frame}: denoise {applied["denoise"]:g}%, '
              f'deblotch {applied["deblotch"]:g}%, color {applied["color"]:g}% ({method})')
    except RestorationInterrupted:
        _metadata(p, pp.index, {'status': 'Interrupted'})
        _fail(p, 'Restoration interrupted before completion.', 'interrupted')
    except Exception as exc:
        _metadata(p, pp.index, {'status': 'Failed'})
        _fail(p, str(exc))
        raise


def finish(p, processed, settings):
    current = getattr(p, PASS, None)
    if not settings.enabled or current is None:
        return
    try:
        if current.owns_color:
            p.color_corrections = current.color_corrections
        if current.failed:
            # Ordinary hook exceptions are swallowed by Neo. Return no failed
            # pass as a usable feedback image to an external script.
            processed.images = []
            processed.infotexts = []
            processed.index_of_first_image = 0
            processed.info = 'Stable Shift stopped: '+current.session.report.get('error', 'Restoration did not complete.')
        else:
            current.session.report['status'] = 'completed'
        _write_report(current.session)
        if current.session.directory is not None:
            processed.comments += f'\nStable Shift comparison files: {current.session.directory}'
    finally:
        setattr(p, PASS, None)
