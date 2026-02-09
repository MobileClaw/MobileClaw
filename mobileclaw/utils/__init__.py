# The util functions in this package is to be used by framework developers.
# If you want to add a tool for users (i.e. agent developers), do it in the `tools` package.
from .image_utils import (
    wrap_text_to_width,
    load_cjk_font,
    get_annotation_font,
    annotate_image_with_top_text,
    resize_to_height,
    horizontally_concat_images,
    image_to_base64_url,
)

from .scrcpy_recorder import ScrcpyRecorder

import datetime

class TimeUtils:
    @staticmethod
    def current_timestamp():
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return timestamp
    
    @staticmethod
    def time_now():
        return datetime.datetime.now()

def sanitize_filename(filename: str, max_length: int = 80) -> str:
    """Sanitize filename by removing unsafe characters and limiting length.

    Args:
        filename: Original filename.
        max_length: Maximum length (excluding extension), defaults to 80 characters.

    Returns:
        str: Sanitized safe filename.
    """
    unsafe_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|', '\n', '\r', '\t', ';']
    for char in unsafe_chars:
        filename = filename.replace(char, '_')

    if len(filename) > max_length:
        filename = filename[:max_length]

    filename = filename.rstrip(' .')
    return filename