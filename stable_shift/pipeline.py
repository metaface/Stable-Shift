"""The single retained path: automatic analysis, SCUNet, deblotching, color."""
from dataclasses import dataclass, asdict
from time import perf_counter
import numpy as np

from .automatic import analyze_noise, analyze_surfaces
from .deblotch import cleanup_candidates
from .global_color import fit_reference_color, METHODS
from .preview import Preview, blend, image_signature, strength
from .scunet import denoise


@dataclass(frozen=True)
class Options:
    automatic: bool = True
    denoise: float = 100
    deblotch: float = 100
    color: float = 100
    reference: bool = True
    color_method: str = 'Robust global'

    def validate(self):
        strength(self.denoise)
        strength(self.deblotch, 200)
        strength(self.color)
        if self.color_method not in METHODS:
            raise ValueError('Unknown color method: '+str(self.color_method))
        return self


@dataclass(frozen=True)
class ModelCache:
    signature: str
    rgb: np.ndarray
    report: dict


def prepare(reference, edited, options=Options(), progress=None, *, cached=None):
    options.validate()
    started = perf_counter()
    source = np.asarray(edited.convert('RGB')).copy()
    signature = image_signature(edited)
    if progress:
        progress('Analyzing image noise')
    noise = analyze_noise(source)
    dose = noise['denoise'] if options.automatic else float(options.denoise)
    reused = False
    cache = cached
    model_report = {'skipped': True, 'reason': 'No denoising requested by analysis or manual control.'}
    if dose:
        if cached is not None and cached.signature == signature:
            model_rgb, model_report, reused = cached.rgb, cached.report, True
        else:
            model_rgb, model_report = denoise(source, progress)
            if model_rgb.dtype != np.uint8 or model_rgb.shape != source.shape:
                raise ValueError('SCUNet must return native-size uint8 RGB pixels.')
            model_rgb = np.array(model_rgb, copy=True)
            model_rgb.flags.writeable = False
            cache = ModelCache(signature, model_rgb, dict(model_report))
        working = blend(source, model_rgb, dose)
    else:
        working = source.copy()
        if cache is not None and cache.signature != signature:
            cache = None
    if progress:
        progress('Preparing deblotching and reference colors')
    regular, strong, cleanup_report = cleanup_candidates(working, progress)
    transform, color_report = fit_reference_color(reference, working, method=options.color_method,
        enabled=options.reference and reference is not None)
    endpoints = (working, regular, strong)
    colored = tuple(a.copy() if transform is None else transform.apply(a) for a in endpoints)
    if progress:
        progress('Analyzing remaining surface variation')
    surfaces = analyze_surfaces(colored[0])
    delta = np.abs(colored[0].astype(np.int16)-working)
    reference_dose = 100. if transform is not None and (delta.mean() >= .25 or np.percentile(delta, 95) >= 1) else 0.
    recommended = {'denoise': noise['denoise'], 'deblotch': surfaces['deblotch'], 'color': reference_dose}
    applied = recommended if options.automatic else {'denoise': dose,
        'deblotch': float(options.deblotch), 'color': float(options.color) if transform is not None else 0.}
    report = {'version': '2.24', 'backend': 'SCUNet', 'options': asdict(options),
        'input_signatures': {'edited': signature, 'reference': image_signature(reference) if reference is not None else None},
        'analysis': {'noise': noise, 'surfaces': surfaces}, 'recommended': recommended,
        'prepared_strengths': applied, 'color_correction': color_report,
        'scunet': dict(model_report), 'model_reused': reused,
        'deblotching': cleanup_report, 'preparation_seconds': perf_counter()-started,
        'note': 'Automatic analysis chooses strengths; it is not semantic recognition of intentional texture. Manual deblotch/color previews reuse fixed endpoints. Denoise/method changes require Run and reuse matching model inference.'}
    return Preview(endpoints, colored, report, cache)


def restore(reference, edited, options=Options(), progress=None):
    return prepare(reference, edited, options, progress).render()
