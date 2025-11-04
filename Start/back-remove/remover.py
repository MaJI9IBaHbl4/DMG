# remover.py
# pip install backgroundremover
from backgroundremover.bg import remove
from pathlib import Path
import argparse

def remove_bg(input_path: str) -> str:
    """Удаляет фон у изображения и сохраняет PNG в results/<stem>_no_bg.png."""
    inp = Path(input_path)
    if not inp.exists():
        raise FileNotFoundError(f"Input not found: {inp}")

    out_dir = Path("results")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{inp.stem}_no_bg.png"

    # ВАЖНО: передаём байты (совместимо с вашей версией библиотеки)
    with open(inp, "rb") as f:
        img_bytes = f.read()

    png_bytes = remove(img_bytes)  # без file_path/path — просто байты
    with open(out_path, "wb") as f:
        f.write(png_bytes)

    return str(out_path)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Remove image background and save to results/")
    parser.add_argument("image", help="Path to input image (jpg/png/webp...)")
    args = parser.parse_args()

    saved_to = remove_bg(args.image)
    print(f"✅ Saved: {saved_to}")
