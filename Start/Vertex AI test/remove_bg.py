#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

import vertexai
from vertexai.preview.vision_models import Image, ImageGenerationModel

def remove_background_vertex(input_path: str, output_path: str, project_id: str, location: str = "us-central1"):
    import vertexai
    from vertexai.preview.vision_models import Image, ImageGenerationModel

    vertexai.init(project=project_id, location=location)

    base_img = Image.load_from_file(location=input_path)
    model = ImageGenerationModel.from_pretrained("imagegeneration@006")

    images = model.edit_image(
        base_image=base_img,
        mask_mode="background",          # auto-сегментация фона
        edit_mode="inpainting-remove",   # «удалить» содержимое в зоне маски
        prompt="remove background",      # ОБЯЗАТЕЛЕН даже для remove
    )

    images[0].save(location=output_path, include_generation_parameters=False)


def main():
    p = argparse.ArgumentParser(description="Remove image background with Vertex AI Imagen Editing")
    p.add_argument("--input", required=True, help="Путь к исходному изображению с фоном")
    p.add_argument("--output", required=True, help="Имя/путь выходного файла PNG без фона")
    p.add_argument("--project", required=True, help="GCP project id (для Vertex AI)")
    p.add_argument("--location", default="us-central1", help="Vertex AI region (по умолчанию us-central1)")
    args = p.parse_args()

    # Быстрая валидация
    if not Path(args.input).exists():
        print(f"Файл не найден: {args.input}", file=sys.stderr)
        sys.exit(1)

    try:
        remove_background_vertex(args.input, args.output, args.project, args.location)
        print(f"OK: фон удалён → {args.output}")
    except Exception as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        sys.exit(2)

if __name__ == "__main__":
    main()