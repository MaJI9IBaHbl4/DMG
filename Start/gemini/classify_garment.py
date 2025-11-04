#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse, json, mimetypes, os, sys, time, datetime
from pathlib import Path
from typing import Dict, Any, List, Tuple

# --- Gemini (Vertex AI) ---
from google import genai
from google.genai import types as gx

# =======================
# Таксономия (2 уровня)
# =======================
COARSE: List[str] = [
    "top","bottom","dress_jumpsuit","outerwear","footwear",
    "accessory","underwear_sleep","sports_swim","sets","other"
]

FINE_BY_COARSE: Dict[str, List[str]] = {
    "top": [
        "t_shirt","polo_shirt","shirt_buttoned","blouse",
        "tank_top","longsleeve","sweatshirt","hoodie",
        "sweater_knit","cardigan","vest_top","crop_top","bodysuit_top"
    ],
    "bottom": [
        "jeans","pants_chinos","trousers_tailored","shorts",
        "skirt_mini","skirt_midi","skirt_maxi","leggings","joggers","sweatpants"
    ],
    "dress_jumpsuit": [
        "dress_mini","dress_midi","dress_maxi","jumpsuit_full","playsuit_romper"
    ],
    "outerwear": [
        "jacket_light","denim_jacket","leather_jacket","coat","trench_coat",
        "down_puffer","parka","blazer"
    ],
    "footwear": [
        "sneakers","boots_ankle","boots_knee","loafers","heels","sandals","slippers"
    ],
    "accessory": [
        "bag_tote","bag_crossbody","backpack","belt","scarf",
        "hat_beanie","cap_baseball","gloves"
    ],
    "underwear_sleep": [
        "bra","panties","boxers_briefs","socks","tights","pajama_set","robe"
    ],
    "sports_swim": [
        "sports_top","sports_leggings","tracksuit_top","tracksuit_bottom",
        "swimsuit_onepiece","bikini_top","bikini_bottom","swim_trunks"
    ],
    "sets": [
        "suit_set","tracksuit_set","pajama_set_two_piece"
    ],
    "other": [
        "costume","ethnic_traditional","workwear_uniform","maternity","other"
    ],
}

ALL_FINE: List[str] = sorted({f for lst in FINE_BY_COARSE.values() for f in lst})
FINE_TO_COARSE: Dict[str, str] = {f: c for c, lst in FINE_BY_COARSE.items() for f in lst}

# =======================
# Атрибуты
# =======================
PATTERN_ENUM = ["solid","striped","checked","floral","graphic","polka_dot","other"]
SLEEVE_ENUM  = ["sleeveless","short","three_quarter","long","unknown"]
NECKLINE_ENUM = ["crew","v_neck","scoop","turtleneck","polo","button_down","strapless","other"]

# НОВОЕ: длина брюк и тип кромки
PANT_LENGTH_ENUM = ["floor_sweeping", "full", "ankle", "cropped", "capri", "unknown"]
HEM_FINISH_ENUM  = ["clean", "raw", "rolled_cuff", "elastic_cuff", "frayed", "other"]

def must_file(p: str) -> str:
    path = Path(p)
    if not path.exists():
        raise SystemExit(f"Файл не найден: {p}")
    return str(path)

def build_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "title": "GarmentAttributesV2",
        "additionalProperties": False,
        "required": ["coarse_category","fine_category"],
        "properties": {
            "coarse_category": {"type": "string", "enum": COARSE},
            "fine_category":   {"type": "string", "enum": ALL_FINE},
            "pattern":         {"type": "string", "enum": PATTERN_ENUM},
            "sleeve_length":   {"type": "string", "enum": SLEEVE_ENUM},
            "neckline":        {"type": "string", "enum": NECKLINE_ENUM},
            "material_guess":  {"type": "string"},
            "notes":           {"type": "string"},

            # НОВОЕ: не обязательные поля
            "pant_length":     {"type": "string", "enum": PANT_LENGTH_ENUM},
            "hem_finish":      {"type": "string", "enum": HEM_FINISH_ENUM},
        },
    }

GLOSSARY = (
    "Disambiguation rules (choose strictly from the enum):\n"
    "\n"
    "— BASIC PRINCIPLES —\n"
    "* First pick coarse_category, then pick fine_category ONLY from those allowed for the chosen coarse.\n"
    "* If the garment combines top+bottom as a single piece → dress_*. If they are separate pieces → top + bottom.\n"
    "* When in doubt, choose the most general/conservative option.\n"
    "* Do not invent new values; use the closest enum.\n"
    "\n"
    "— TOP —\n"
    "* hoodie = sweatshirt WITH a hood. If there is no hood → sweatshirt.\n"
    "* sweatshirt = sweatshirt/fleece (loopback jersey), WITHOUT buttons and WITHOUT a collar. Thin knit with visible loops → sweater_knit.\n"
    "* sweater_knit = knitwear (loops visible). If there is a full-length front opening → cardigan.\n"
    "* cardigan = knit top with a front opening (buttons/zip). If no opening → sweater_knit.\n"
    "* shirt_buttoned = button-front shirt with a collar. If there is no collar and it is jersey knit → t_shirt/longsleeve.\n"
    "* t_shirt = short sleeves, crew or V neck, no collar, no buttons.\n"
    "* longsleeve = like t_shirt but with long sleeves.\n"
    "* polo_shirt = knit tee with a SHORT placket and a fold-over collar.\n"
    "* blouse = lightweight/flowy fabric (chiffon/satin), often a feminine cut; if a formal office shirt with collar and placket → shirt_buttoned.\n"
    "* tank_top = sleeveless with open shoulders. If very short and exposes midriff → crop_top.\n"
    "* vest_top = sleeveless vest (top). Do NOT confuse with a tailored suit vest (if part of a suit — see sets/blazer).\n"
    "* bodysuit_top = one-piece top with a bottom closure; body-hugging.\n"
    "\n"
    "— BOTTOM —\n"
    "* jeans = denim with typical details (five pockets, rivets). If not denim → pants_chinos/trousers_tailored.\n"
    "* pants_chinos = cotton/casual trousers without pressed creases, soft fabric.\n"
    "* trousers_tailored = dress/suiting trousers (pressed creases, fly, belt loops, suiting fabric).\n"
    "* joggers = cuffs/elastic at hem and waistband, sporty/casual cut. If no cuffs → sweatpants.\n"
    "* leggings = elastic, very form-fitting, no fly/pockets.\n"
    "* skirt_* = separate lower garment. If it is a single piece covering top+bottom → dress_*.\n"
    "\n"
    "— DRESS/JUMPSUIT —\n"
    "* dress_* = single-piece garment covering top and bottom, not divided into trousers.\n"
    "* jumpsuit_full = one-piece jumpsuit with trouser legs. Short version with shorts → playsuit_romper.\n"
    "* Choose dress_mini/midi/maxi by hem length (roughly above knee / mid-calf / below ankle).\n"
    "\n"
    "— OUTERWEAR —\n"
    "* blazer = tailored jacket with lapels in suiting fabric; formal cut. Do not confuse with a casual jacket.\n"
    "* jacket_light = lightweight jacket without clear blazer features; windbreaker/bomber, etc.\n"
    "* denim_jacket = denim jacket (denim, patch pockets).\n"
    "* leather_jacket = leather/faux-leather, biker/classic cuts.\n"
    "* coat = coat to knee length or longer, without puffer quilting. trench_coat = coat with epaulettes/belt/storm flap, woven shell.\n"
    "* down_puffer = quilted insulated/puffer outerwear. parka = longer length, hood, often fur trim.\n"
    "\n"
    "— FOOTWEAR —\n"
    "* sneakers = athletic/casual shoes with a flexible sole.\n"
    "* boots_ankle/knee = ankle boots / knee-high boots.\n"
    "* loafers = slip-on leather/suede, smart-casual. heels = high-heeled pumps.\n"
    "* sandals = open shoes with straps. slippers = house slides/mules (open back).\n"
    "\n"
    "— ACCESSORY —\n"
    "* bag_tote = large tote with two handles; bag_crossbody = small crossbody with a long strap; backpack = rucksack.\n"
    "* hat_beanie = knit beanie; cap_baseball = baseball cap; scarf = scarf; belt = belt; gloves = gloves.\n"
    "\n"
    "— UNDERWEAR/SLEEP —\n"
    "* bra, panties, boxers_briefs, socks, tights — by obvious features.\n"
    "* pajama_set/robe — home/sleepwear. If it is a 2-piece set → pajama_set_two_piece (under sets).\n"
    "\n"
    "— SPORTS/SWIM —\n"
    "* sports_top/leggings/tracksuit_* — technical/elastic materials, sporty cut.\n"
    "* swimsuit_onepiece = one-piece swimsuit; bikini_top/bottom = two-piece; swim_trunks = men's swim shorts.\n"
    "\n"
    "— SETS —\n"
    "* suit_set = blazer + trousers/skirt as one suit. tracksuit_set = tracksuit (top+bottom).\n"
    "\n"
    "— PANTS LENGTH —\n"
    "* floor_sweeping = hem touches floor and pools.\n"
    "* full = hem reaches shoe/heel (no ankle visible).\n"
    "* ankle = ankle bone visible.\n"
    "* cropped = several cm above ankle.\n"
    "* capri = around mid-calf.\n"
    "* unknown = hem not visible.\n"
    "\n"
    "— HEM FINISH —\n"
    "* clean (finished), raw (cut edge), rolled_cuff (turn-ups), elastic_cuff, frayed (distressed), other.\n"
    "\n"
    "— EDGE CASES —\n"
    "* If fine is chosen but coarse does not match — coarse must follow the fine→coarse map.\n"
    "* If multiple items are visible, classify the MAIN item (largest/center). Do not mix categories.\n"
    "* If the item clearly does not fit any enum — use 'other' within the relevant group.\n"
)

def analyze_with_gemini(image_path: str, mime_type: str, project: str, location: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    client = genai.Client(vertexai=True, project=project, location=location)

    schema = build_schema()
    instruction = (
        "You are a fashion tagger. Look at ONE garment on plain background.\n"
        "Step 1: choose coarse_category from enum strictly.\n"
        "Step 2: choose fine_category from enum that belongs to the chosen coarse_category only.\n"
        "If unsure, choose the closest enum; do NOT invent values. Do NOT infer color.\n\n"
        f"{GLOSSARY}"
    )

    # Рассчитываем «вес» запроса
    instruction_bytes = len(instruction.encode("utf-8"))
    schema_bytes = len(json.dumps(schema, ensure_ascii=False).encode("utf-8"))

    with open(image_path, "rb") as f:
        image_bytes = f.read()
    image_size = len(image_bytes)

    resp = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[instruction, gx.Part.from_bytes(data=image_bytes, mime_type=mime_type)],
        config=gx.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=schema,
            temperature=0.2,
        ),
    )

    # Текст/объём ответа
    if hasattr(resp, "parsed") and resp.parsed:
        attrs = dict(resp.parsed)
        resp_text_for_size = json.dumps(attrs, ensure_ascii=False)
    else:
        attrs = json.loads(resp.text)
        resp_text_for_size = resp.text

    response_bytes = len(resp_text_for_size.encode("utf-8"))

    # Токены: берём, если SDK их вернул
    usage = getattr(resp, "usage", None) or getattr(resp, "usage_metadata", None) or {}
    input_tokens  = getattr(usage, "input_tokens",  None) if hasattr(usage, "input_tokens")  else usage.get("input_tokens")  if isinstance(usage, dict) else None
    output_tokens = getattr(usage, "output_tokens", None) if hasattr(usage, "output_tokens") else usage.get("output_tokens") if isinstance(usage, dict) else None
    total_tokens  = getattr(usage, "total_tokens",  None) if hasattr(usage, "total_tokens")  else usage.get("total_tokens")  if isinstance(usage, dict) else None

    debug = {
        "instruction_bytes": instruction_bytes,
        "schema_bytes": schema_bytes,
        "image_bytes": image_size,
        "request_bytes_total": instruction_bytes + schema_bytes + image_size,
        "response_bytes": response_bytes,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "model": "gemini-2.5-flash",
    }

    return attrs, debug

def validate_and_fix(categories: Dict[str, Any]) -> Dict[str, Any]:
    coarse = categories.get("coarse_category")
    fine   = categories.get("fine_category")

    if fine not in FINE_TO_COARSE:
        print(f"[warn] fine_category '{fine}' не распознан — заменяю на 'other'", file=sys.stderr)
        categories["fine_category"] = "other"
        categories["coarse_category"] = "other"
        return categories

    expected_coarse = FINE_TO_COARSE[fine]
    if coarse != expected_coarse:
        print(f"[warn] coarse_category '{coarse}' не соответствует fine '{fine}' — исправляю на '{expected_coarse}'", file=sys.stderr)
        categories["coarse_category"] = expected_coarse

    return categories

# =======================
# CLI
# =======================
def main():
    ap = argparse.ArgumentParser(description="Gemini: 2-уровневая классификация одежды (без цвета)")
    ap.add_argument("image", type=must_file, help="Путь к изображению (можно UNC)")
    ap.add_argument("--project",  default=os.getenv("GOOGLE_CLOUD_PROJECT"), help="GCP project id")
    ap.add_argument("--location", default=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"), help="Vertex AI location")
    ap.add_argument("--print",    dest="print_mode", choices=["all","time"], default="all",
                    help="Что печатать в консоль: all — весь JSON, time — только время и путь")
    args = ap.parse_args()

    if not args.project:
        raise SystemExit("Не задан project. Передайте --project или установите переменную GOOGLE_CLOUD_PROJECT.")

    t0 = time.time()

    mime_type, _ = mimetypes.guess_type(args.image)
    if mime_type is None:
        ext = Path(args.image).suffix.lower()
        mime_type = "image/png" if ext == ".png" else "image/jpeg"

    # 1) Модель + расчёт «веса» запроса
    attrs, dbg = analyze_with_gemini(args.image, mime_type, project=args.project, location=args.location)

    # 2) Валидируем согласованность
    attrs = validate_and_fix(attrs)

    elapsed = round(time.time() - t0, 3)
    analysis_date = datetime.date.today().isoformat()

    # 3) Итоговый JSON (без метаданных)
    result = {
        "analysis_date": analysis_date,
        "input_image_path": str(Path(args.image).resolve()),
        "coarse_category": attrs.get("coarse_category", "other"),
        "fine_category":   attrs.get("fine_category", "other"),
        "pattern":         attrs.get("pattern"),
        "sleeve_length":   attrs.get("sleeve_length"),
        "neckline":        attrs.get("neckline"),
        "material_guess":  attrs.get("material_guess"),
        "pant_length":     attrs.get("pant_length"),   # НОВОЕ
        "hem_finish":      attrs.get("hem_finish"),    # НОВОЕ
        "notes":           attrs.get("notes"),
        "elapsed_seconds": elapsed,
    }

    # 4) Сохранение: results/<stem>_<YYYYmmdd_HHMMSS>.json
    out_dir = Path("results")
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"{Path(args.image).stem}_{ts}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # 5) Вывод результата
    if args.print_mode == "all":
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print(f"\n✅ Saved: {out_path.resolve()}")
    else:
        print(f"elapsed_seconds={elapsed}  saved_to={out_path.resolve()}")

    # 6) Детальный «вес» запроса (всегда выводим ниже)
    def _kb(n): return f"{n/1024:.2f} KB"
    print("\n--- Request/Response weight ---")
    print(f"model: {dbg.get('model')}")
    print(f"instruction_bytes: {dbg['instruction_bytes']} ({_kb(dbg['instruction_bytes'])})")
    print(f"schema_bytes:      {dbg['schema_bytes']} ({_kb(dbg['schema_bytes'])})")
    print(f"image_bytes:       {dbg['image_bytes']} ({_kb(dbg['image_bytes'])})")
    print(f"request_total:     {dbg['request_bytes_total']} ({_kb(dbg['request_bytes_total'])})")
    print(f"response_bytes:    {dbg['response_bytes']} ({_kb(dbg['response_bytes'])})")
    if dbg.get("total_tokens") is not None or dbg.get("input_tokens") is not None:
        print(f"tokens: input={dbg.get('input_tokens')} output={dbg.get('output_tokens')} total={dbg.get('total_tokens')}")

if __name__ == "__main__":
    main()
