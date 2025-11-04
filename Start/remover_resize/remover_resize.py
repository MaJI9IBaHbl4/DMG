# remover_resize.py
# pip install backgroundremover pillow

from backgroundremover.bg import remove
from pathlib import Path
from io import BytesIO
from PIL import Image
import argparse

def downscale_to_max_edge(image_bytes: bytes, max_edge: int = 1536) -> bytes:
    """
    Если изображение больше max_edge по длинной стороне — уменьшаем с сохранением пропорций.
    Если меньше/равно — возвращаем как есть. Сохраняем без потерь (PNG).
    """
    im = Image.open(BytesIO(image_bytes))
    im.load()  # гарантированно читаем в память (важно для некоторых форматов/стримов)

    w, h = im.size
    longer = max(w, h)
    if longer <= max_edge:
        return image_bytes  # ничего не делаем, чтобы не трогать качество/метаданные

    if w >= h:
        new_w = max_edge
        new_h = int(h * (max_edge / w))
    else:
        new_h = max_edge
        new_w = int(w * (max_edge / h))

    im = im.resize((new_w, new_h), resample=Image.LANCZOS)

    buf = BytesIO()
    # PNG: без потерь, оптимизация по размеру файла
    im.save(buf, format="PNG", optimize=True, compress_level=9)
    return buf.getvalue()

def remove_bg(input_path: str, max_edge: int = 1536) -> str:
    """
    Удаляет фон у изображения: предварительно даунскейлит до max_edge (если нужно),
    сохраняет как PNG в results/<stem>_no_bg.png. Возвращает путь к сохранённому файлу.
    """
    inp = Path(input_path)
    if not inp.exists():
        raise FileNotFoundError(f"Input not found: {inp}")

    # читаем исходник
    with open(inp, "rb") as f:
        img_bytes = f.read()

    # мягко сжимаем до логического размера (только даунскейл, без апскейла)
    resized_bytes = downscale_to_max_edge(img_bytes, max_edge=max_edge)

    # удаляем фон (на вход подаём bytes)
    out_png_bytes = remove(resized_bytes)

    # сохраняем результат
    out_dir = Path("results")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{inp.stem}_no_bg.png"
    with open(out_path, "wb") as f:
        f.write(out_png_bytes)

    return str(out_path)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Remove background with logical downscale (no quality loss).")
    parser.add_argument("image", help="Path to input image (jpg/png/webp...)")
    parser.add_argument("--max-edge", type=int, default=1536,
                        help="Max size of the long edge in pixels (default: 1536). Only downscales, never upscales.")
    args = parser.parse_args()

    saved_to = remove_bg(args.image, max_edge=args.max_edge)
    print(f"✅ Saved: {saved_to}")
