# remover_resize.py
# pip install backgroundremover pillow

from backgroundremover.bg import remove
from pathlib import Path
from io import BytesIO
from PIL import Image
import argparse


def crop_to_content(im: Image.Image, alpha_threshold: int = 0) -> Image.Image:
    """
    Обрезаем изображение по непрозрачным пикселям (по альфе).
    Если альфа нет — возвращаем как есть.
    """
    # Приводим к формату с альфой, если возможно
    if im.mode == "P" and "transparency" in im.info:
        im = im.convert("RGBA")

    if im.mode not in ("RGBA", "LA"):
        # Нет альфы — обрезать по прозрачности нечем
        return im

    alpha = im.split()[-1]  # альфа-канал

    # Делаем бинарную маску: всё, что > threshold, считаем "контентом"
    mask = alpha.point(lambda px: 255 if px > alpha_threshold else 0)
    bbox = mask.getbbox()

    if bbox is None:
        # Ничего не нашли (всё прозрачно?) — возвращаем как есть
        return im

    return im.crop(bbox)


def flatten_alpha(im: Image.Image, bg_color=(255, 255, 255)) -> Image.Image:
    """
    Убираем альфа-канал:
    - если есть прозрачность, композитим на сплошной фон bg_color
    - возвращаем обычное RGB
    """
    if im.mode == "P" and "transparency" in im.info:
        im = im.convert("RGBA")

    if im.mode in ("RGBA", "LA"):
        im = im.convert("RGBA")
        alpha = im.split()[-1]
        bg = Image.new("RGB", im.size, bg_color)
        bg.paste(im, mask=alpha)
        return bg

    if im.mode != "RGB":
        im = im.convert("RGB")

    return im


def downscale_pil_to_max_edge(im: Image.Image, max_edge: int = 1536) -> Image.Image:
    """
    Даунскейл PIL-изображения до max_edge по длинной стороне.
    Если изображение меньше/равно — возвращаем как есть.
    """
    w, h = im.size
    longer = max(w, h)
    if longer <= max_edge:
        return im

    if w >= h:
        new_w = max_edge
        new_h = int(h * (max_edge / w))
    else:
        new_h = max_edge
        new_w = int(w * (max_edge / h))

    return im.resize((new_w, new_h), resample=Image.LANCZOS)


def remove_bg(input_path: str, max_edge: int = 1536) -> str:
    """
    Пайплайн:
    1) читаем исходное изображение
    2) удаляем фон (backgroundremover.remove) -> PNG с альфой
    3) обрезаем по непрозрачным пикселям (crop_to_content)
    4) убираем альфу (flatten_alpha)
    5) даунскейлим (downscale_pil_to_max_edge)
    6) сохраняем в results/<stem>_no_bg.png
    """
    inp = Path(input_path)
    if not inp.exists():
        raise FileNotFoundError(f"Input not found: {inp}")

    # 1) читаем исходник
    with open(inp, "rb") as f:
        img_bytes = f.read()

    # 2) удаляем фон (на вход подаём bytes)
    out_png_bytes = remove(img_bytes)

    # 3) открываем результат через PIL
    im = Image.open(BytesIO(out_png_bytes))
    im.load()

    # обрезаем по альфе, чтобы не было лишнего
    im = crop_to_content(im, alpha_threshold=0)

    # 4) убираем альфа-канал (делаем обычное RGB)
    im = flatten_alpha(im, bg_color=(255, 255, 255))  # фон — белый

    # 5) даунскейлим результат
    im = downscale_pil_to_max_edge(im, max_edge=max_edge)

    # 6) сохраняем результат
    out_dir = Path("results")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{inp.stem}_no_bg.png"
    im.save(out_path, format="PNG", optimize=True, compress_level=9)

    return str(out_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Remove background, crop, drop alpha, then downscale.")
    parser.add_argument("image", help="Path to input image (jpg/png/webp...)")
    parser.add_argument(
        "--max-edge",
        type=int,
        default=1536,
        help="Max size of the long edge in pixels (default: 1536). Only downscales, never upscales.",
    )
    args = parser.parse_args()

    saved_to = remove_bg(args.image, max_edge=args.max_edge)
    print(f"✅ Saved: {saved_to}")
