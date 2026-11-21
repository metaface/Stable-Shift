"""Native PNG/settings saves and a small, prioritized test bundle."""
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from PIL import Image
from .preview import image_signature


def save_result(image, report, path):
    path = Path(path)
    image.save(path)
    path.with_suffix('.settings.json').write_text(json.dumps(report, indent=2), encoding='utf-8')


def save_test(preview, image, report, source, reference, directory):
    signatures = report['input_signatures']
    if image_signature(source) != signatures['edited'] or (
            reference is not None and image_signature(reference) != signatures['reference']):
        raise ValueError('The inputs have changed since this result was prepared.')
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    source.save(directory/'edited_source.png')
    image.save(directory/'result.png')
    required = ['edited_source.png', 'result.png']
    if reference is not None:
        reference.save(directory/'color_reference.png')
        required.append('color_reference.png')
    optional = []
    if preview.cache is not None and preview.cache.signature == signatures['edited']:
        Image.fromarray(preview.cache.rgb).save(directory/'scunet_before_color.png')
        optional.append('scunet_before_color.png')
    data = dict(report)
    budget = 30*1024*1024-200_000-len(json.dumps(data).encode())
    used = sum((directory/n).stat().st_size for n in required)
    included, omitted = required.copy(), []
    for name in optional:
        size = (directory/name).stat().st_size
        if used+size <= budget:
            used += size
            included.append(name)
        else:
            omitted.append(name)
    archive = directory/'share_test.zip' if used <= budget else None
    data.update(share_files=included if archive else [], omitted_optional_files=omitted)
    (directory/'settings.json').write_text(json.dumps(data, indent=2), encoding='utf-8')
    if archive:
        with ZipFile(archive, 'w', compression=ZIP_DEFLATED) as z:
            for name in included+['settings.json']:
                z.write(directory/name, name)
        if archive.stat().st_size > 30*1024*1024:
            archive.unlink()
            archive = None
    return archive or directory
