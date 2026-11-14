"""Image loading shared by file dialogs and native file drops."""
from pathlib import Path
import os
from urllib.parse import unquote, urlsplit

from PIL import Image, ImageOps


def drop_path(tcl, payload):
    """Parse Tcl's file list; don't split paths on spaces or strip braces by hand."""
    paths = tcl.splitlist(payload)
    if len(paths) != 1:
        raise ValueError('Drop one image at a time onto each input panel.')
    value = paths[0]
    if value.lower().startswith('file:'):
        uri = urlsplit(value)
        value = unquote(uri.path)
        if uri.netloc and uri.netloc != 'localhost':
            value = '//' + uri.netloc + value
        elif os.name == 'nt' and len(value) > 2 and value[0] == '/' and value[2] == ':':
            value = value[1:]
    return Path(value)


def load_image(path):
    path = Path(path)
    if not path.is_file():
        raise ValueError('Drop an image file, rather than a folder.')
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert('RGB')
        image.load()
    return image
