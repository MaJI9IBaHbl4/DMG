from pathlib import Path
import argparse, os, time, datetime, math, random
from google import genai
from google.genai.types import Image, RecontextImageSource, ProductImage

MAX_PER_CALL = 4  # обычно до 4 изображений за вызов

def must_file(p):
    p = Path(p)
    if not p.exists():
        raise SystemExit(f"Файл не найден: {p}")
    return str(p)

def save_variants(resp, out_dir, ts, start_idx=0):
    saved = 0
    for i, gi in enumerate(getattr(resp, "generated_images", []) or []):
        img = gi.image
        idx = start_idx + i + 1
        out_path = Path(out_dir) / f"result_{ts}_{idx:02d}.png"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(out_path)
        print(f"✅ сохранён вариант #{idx}: {out_path.resolve()}")
        saved += 1
    return saved

def main():
    ap = argparse.ArgumentParser(description="Virtual Try-On через Vertex AI (несколько вариантов)")
    ap.add_argument("--person",   required=True, type=must_file)
    ap.add_argument("--garment",  required=True, type=must_file)
    ap.add_argument("--project",  default=os.getenv("GOOGLE_CLOUD_PROJECT"))
    ap.add_argument("--location", default=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"))
    ap.add_argument("--count",    type=int, default=6)
    ap.add_argument("--outdir",   default="results")
    ap.add_argument("--seed",     type=int, default=None, help="Использовать seed (только с --no-watermark)")
    ap.add_argument("--no-watermark", action="store_true", help="Отключить watermark (тогда можно seed)")
    args = ap.parse_args()

    if not args.project:
        raise SystemExit("Не задан GOOGLE_CLOUD_PROJECT (или --project).")

    print(f"Vertex config → project={args.project}, location={args.location}")
    client = genai.Client(vertexai=True, project=args.project, location=args.location)

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.outdir) / ts

    total = max(1, args.count)
    batches = math.ceil(total / MAX_PER_CALL)
    remaining = total
    saved_total = 0
    t0 = time.time()

    src = RecontextImageSource(
        person_image=Image.from_file(location=args.person),
        product_images=[ProductImage(product_image=Image.from_file(location=args.garment))],
    )

    # базовый seed, если понадобится
    base_seed = args.seed if args.seed is not None else random.randint(1, 10_000_000)

    for b in range(batches):
        want = min(remaining, MAX_PER_CALL)

        # собираем config на батч
        cfg = {"number_of_images": want}
        if args.no_watermark:
            cfg["add_watermark"] = False
            if args.seed is not None:
                cfg["seed"] = base_seed + b
        elif args.seed is not None:
            print("⚠️ seed игнорируется, потому что watermark включён. "
                  "Если нужен seed — добавьте флаг --no-watermark.")

        print(f"— батч {b+1}/{batches}: запрашиваем {want} изображений"
              f"{' (seed=' + str(cfg.get('seed')) + ')' if 'seed' in cfg else ''}"
              f"{' [no watermark]' if args.no_watermark else ''}")

        resp = client.models.recontext_image(
            model="virtual-try-on-preview-08-04",
            source=src,
            config=cfg,
        )

        saved = save_variants(resp, out_dir, ts, start_idx=saved_total)
        saved_total += saved
        remaining -= want

    dt = time.time() - t0
    print(f"\n🏁 Готово. Сохранено {saved_total} файлов в: {Path(out_dir).resolve()}")
    print(f"🕒 Общее время: {dt:.2f} сек")

if __name__ == "__main__":
    main()
