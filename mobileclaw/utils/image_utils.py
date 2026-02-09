import os
import platform
import subprocess
from typing import List, Tuple

from PIL import Image, ImageDraw, ImageFont


def wrap_text_to_width(text: str, font: ImageFont.ImageFont, max_width: int, draw: ImageDraw.ImageDraw) -> List[str]:
    if not text:
        return [""]
    words = list(text)
    lines: List[str] = []
    current: List[str] = []

    def measure_width(s: str) -> int:
        try:
            return int(draw.textlength(s, font=font))
        except Exception:
            pass
        try:
            bbox = draw.textbbox((0, 0), s, font=font)
            return int(bbox[2] - bbox[0])
        except Exception:
            pass
        try:
            bbox = font.getbbox(s)
            return int(bbox[2] - bbox[0])
        except Exception:
            try:
                bbox_a = font.getbbox("A")
                avg_char_w = int(bbox_a[2] - bbox_a[0])
            except Exception:
                avg_char_w = 8
            return avg_char_w * len(s)

    for ch in words:
        test = "".join(current + [ch])
        w = measure_width(test)
        if w <= max_width:
            current.append(ch)
        else:
            if current:
                lines.append("".join(current))
            current = [ch]
    if current:
        lines.append("".join(current))
    return lines if lines else [text]


def load_cjk_font(font_size: int) -> ImageFont.ImageFont:
    """Attempt to load common CJK fonts across platforms, fallback to default font on failure.

    Args:
        font_size: Font size in points.

    Returns:
        ImageFont.ImageFont: Loaded font object.
    """
    def try_open(path: str) -> ImageFont.ImageFont | None:
        if not path or not os.path.exists(path):
            return None
        if path.lower().endswith('.ttc'):
            for idx in range(0, 8):
                try:
                    return ImageFont.truetype(path, font_size, index=idx)
                except Exception:
                    continue
            return None
        try:
            return ImageFont.truetype(path, font_size)
        except Exception:
            return None

    # 1) Project resources directory
    try:
        base_dir = os.path.dirname(os.path.dirname(__file__))
        res_dir = os.path.join(base_dir, "resources")
        for p in [os.path.join(res_dir, "NotoSansSC-Regular.ttf")]:
            f = try_open(p)
            if f is not None:
                return f
    except Exception:
        pass

    # 2) Platform common paths
    sysname = platform.system().lower()
    common_candidates: list[str] = []
    if sysname == "darwin":
        common_candidates.extend([
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti Medium.ttc",
            "/System/Library/Fonts/STHeiti Light.ttc",
            "/System/Library/Fonts/Supplemental/Songti.ttc",
            "/System/Library/Fonts/Supplemental/NotoSansSC-Regular.otf",
            "/Library/Fonts/Arial Unicode.ttf",
            "/Library/Fonts/Arial Unicode MS.ttf",
        ])
    elif sysname == "windows":
        win_dir = os.environ.get("WINDIR", "C:\\Windows")
        common_candidates.extend([
            os.path.join(win_dir, "Fonts", "msyh.ttc"),
            os.path.join(win_dir, "Fonts", "msyhbd.ttc"),
            os.path.join(win_dir, "Fonts", "SimSun.ttc"),
            os.path.join(win_dir, "Fonts", "simsun.ttc"),
            os.path.join(win_dir, "Fonts", "SimHei.ttf"),
            os.path.join(win_dir, "Fonts", "simhei.ttf"),
            os.path.join(win_dir, "Fonts", "NotoSansSC-Regular.otf"),
        ])
    else:
        common_candidates.extend([
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansSC-Regular.otf",
            "/usr/share/fonts/truetype/arphic/ukai.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        ])

    for p in common_candidates:
        f = try_open(p)
        if f is not None:
            return f

    # 3) Linux: fc-list search
    if sysname == "linux":
        try:
            proc = subprocess.run(["fc-list", ":", "file", "family"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, check=False)
            output = proc.stdout or ""
            prefer_names = [
                "Noto Sans CJK", "Noto Sans SC", "WenQuanYi", "AR PL UKai", "AR PL UMing",
                "Source Han Sans", "Source Han Serif", "SimHei", "SimSun"
            ]
            candidates: list[str] = []
            for line in output.splitlines():
                parts = line.split(":")
                if not parts:
                    continue
                path = parts[0].strip()
                fam = line[line.find(":")+1:].lower()
                for name in prefer_names:
                    if name.lower() in fam:
                        candidates.append(path)
                        break
            seen = set()
            unique_candidates = []
            for p in candidates:
                if p not in seen:
                    seen.add(p)
                    unique_candidates.append(p)
            for p in unique_candidates:
                f = try_open(p)
                if f is not None:
                    return f
        except Exception:
            pass

    # 4) Fallback candidates
    fallback_candidates = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Supplemental/NotoSansSC-Regular.otf",
        "/Library/Fonts/Arial Unicode.ttf",
        "/Library/Fonts/Arial Unicode MS.ttf",
        "C:/Windows/Fonts/msyh.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansSC-Regular.otf",
    ]
    for p in fallback_candidates:
        f = try_open(p)
        if f is not None:
            return f

    return ImageFont.load_default()


def get_annotation_font(image_height: int) -> ImageFont.ImageFont:
    size = max(12, min(48, int(image_height * 0.024)))
    return load_cjk_font(size)


def annotate_image_with_top_text(base_img: Image.Image, text: str) -> Image.Image:
    font = get_annotation_font(base_img.height)
    draw_tmp = ImageDraw.ImageDraw(base_img.copy())
    max_text_width = base_img.width - 20
    lines = wrap_text_to_width(text, font, max_text_width, draw_tmp)
    try:
        ascent, descent = font.getmetrics()
        base_line_height = int(ascent + descent)
    except Exception:
        bbox = font.getbbox("Ag")
        base_line_height = int(bbox[3] - bbox[1])
    line_spacing = max(3, int(base_line_height * 0.18))
    padding_top = 10
    padding_bottom = 12
    padding_h = 12
    text_height = base_line_height * len(lines) + (line_spacing * (len(lines) - 1) if len(lines) > 1 else 0)
    text_block_height = padding_top + text_height + padding_bottom

    new_img = Image.new("RGB", (base_img.width, base_img.height + text_block_height), (255, 255, 255))
    draw = ImageDraw.Draw(new_img)
    y_cursor = padding_top
    for ln in lines:
        draw.text((padding_h, y_cursor), ln, fill=(0, 0, 0), font=font)
        y_cursor += base_line_height + line_spacing
    new_img.paste(base_img, (0, text_block_height))
    return new_img


def resize_to_height(img: Image.Image, target_height: int) -> Image.Image:
    if img.height == target_height:
        return img
    ratio = target_height / float(img.height)
    new_width = max(1, int(img.width * ratio))
    return img.resize((new_width, target_height), Image.LANCZOS)


def horizontally_concat_images(images: List[Image.Image], gap: int = 20, background: Tuple[int, int, int] = (255, 255, 255)) -> Image.Image:
    if not images:
        raise RuntimeError("No images to concatenate")
    total_width = sum(im.width for im in images) + gap * (len(images) - 1)
    max_height = max(im.height for im in images)
    strip = Image.new("RGB", (total_width, max_height), background)
    x_cursor = 0
    for i, im in enumerate(images):
        y_offset = max_height - im.height
        strip.paste(im, (x_cursor, y_offset))
        x_cursor += im.width
        if i < len(images) - 1:
            x_cursor += gap
    return strip


def image_to_base64_url(image):
    """Convert PIL Image to base64 data URL.

    Args:
        image: PIL Image object to convert.

    Returns:
        str: Base64 encoded data URL string.
    """
    image_format = image.format.upper()
    if image_format not in ['JPEG', 'JPG', 'PNG', 'WEBP']:
        image_format = 'JPEG'

    if image.mode == 'P' or image.mode == 'RGBA' and image_format in ['JPEG', 'JPG']:
        image = image.convert('RGB')

    import base64, io
    image_stream = io.BytesIO()
    image.save(image_stream, format=image_format)
    image_base64 = base64.b64encode(image_stream.getvalue()).decode("utf-8")
    base64_url = f'data:image/{image_format.lower()};base64,{image_base64}'
    return base64_url

