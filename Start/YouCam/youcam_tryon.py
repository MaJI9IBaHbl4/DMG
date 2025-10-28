#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Минимальный CLI-скрипт для тестов YouCam/Perfect Corp AI Clothes Try-On.
Принимает 2 параметра: путь к фото человека и путь к фото одежды.
Требуется API-ключ (переменная окружения YCE_API_KEY).
Эндпоинты заданы константами ниже — при необходимости подправьте их под вашу учетку.
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

import requests

# === Настройки API (подредактируйте под вашу среду/аккаунт) ===
# Базовый URL; у некоторых аккаунтов путь может отличаться (например /api, /v1, и т.п.).
YCE_BASE_URL = os.getenv("YCE_BASE_URL", "https://yce.perfectcorp.com")
# Эндпоинты — собраны отдельно, чтобы проще было править под реальную схему у вашего аккаунта.
ENDPOINTS = {
    # Загрузка файлов. В некоторых версиях используется /api/v1.1/file/upload или /file/{type}
    "upload": "/api/v1.1/file/upload",
    # Создание задачи clothes try-on. Может называться /api/v1.1/ai/clothes-tryon или /ai/clothes/tryon
    "create_task": "/api/v1.1/ai/clothes-tryon",
    # Получение статуса задачи: подставьте {task_id}
    "task_status": "/api/v1.1/task/{task_id}",
    # Скачивание файла по file_id (если API выдает id вместо URL)
    "download_file": "/api/v1.1/file/{file_id}/download",
}

# Таймауты/ретраи
POLL_INTERVAL_SEC = float(os.getenv("YCE_POLL_INTERVAL_SEC", "2.0"))
MAX_WAIT_SEC = int(os.getenv("YCE_MAX_WAIT_SEC", "300"))  # 5 минут по умолчанию

def _url(path: str) -> str:
    return (YCE_BASE_URL.rstrip("/") + path)

def _headers() -> Dict[str, str]:
    api_key = os.getenv("YCE_API_KEY")
    if not api_key:
        print("Ошибка: не задан YCE_API_KEY в окружении", file=sys.stderr)
        sys.exit(2)
    return {
        "Authorization": f"Bearer {api_key}",
    }

def upload_file(file_path: Path, ftype: str) -> str:
    """Загрузка файла. Возвращает file_id (или прямой URL, если API его отдает).
    ftype: 'person' или 'cloth' (проверьте в вашей документации: иногда 'user'/'cloth').
    """
    url = _url(ENDPOINTS["upload"])
    # Тип поля и параметров может отличаться в вашей сборке — наиболее частый вариант ниже:
    files = {"file": (file_path.name, file_path.read_bytes())}
    data = {"type": ftype}
    resp = requests.post(url, headers=_headers(), files=files, data=data, timeout=60)
    if resp.status_code >= 400:
        raise RuntimeError(f"Upload failed ({resp.status_code}): {resp.text}")
    payload = resp.json()
    # Попробуем поддержать оба варианта ответа
    file_id = payload.get("file_id") or payload.get("id") or payload.get("data", {}).get("file_id")
    if not file_id and ("url" in payload or ("data" in payload and "url" in payload["data"])):
        # Некоторые API сразу возвращают прямую ссылку
        return payload.get("url") or payload["data"]["url"]
    if not file_id:
        raise RuntimeError(f"Не удалось извлечь file_id из ответа: {payload}")
    return file_id

def create_tryon_task(person_ref: str, cloth_ref: str) -> str:
    """Создает задачу clothes try-on и возвращает task_id."""
    url = _url(ENDPOINTS["create_task"])
    # Поля body могут отличаться: часто встречается схема ниже
    body = {
        "inputs": {
            "person": person_ref,
            "cloth": cloth_ref,
        },
        # Вы можете добавить опции генерации/вариаций здесь, если ваш тариф это поддерживает.
        # "options": {"num_results": 4, "preserve_face": True}
    }
    resp = requests.post(url, headers={**_headers(), "Content-Type": "application/json"}, json=body, timeout=60)
    if resp.status_code >= 400:
        raise RuntimeError(f"Create task failed ({resp.status_code}): {resp.text}")
    payload = resp.json()
    task_id = payload.get("task_id") or payload.get("id") or payload.get("data", {}).get("task_id")
    if not task_id:
        raise RuntimeError(f"Не удалось извлечь task_id из ответа: {payload}")
    return task_id

def wait_for_task(task_id: str) -> Dict[str, Any]:
    """Пуллинг статуса задачи до завершения или таймаута. Возвращает финальный payload."""
    url_tpl = _url(ENDPOINTS["task_status"])
    deadline = time.time() + MAX_WAIT_SEC
    while True:
        url = url_tpl.format(task_id=task_id)
        resp = requests.get(url, headers=_headers(), timeout=30)
        if resp.status_code >= 400:
            raise RuntimeError(f"Task status failed ({resp.status_code}): {resp.text}")
        payload = resp.json()
        status = payload.get("status") or payload.get("data", {}).get("status")
        if status in {"succeeded", "completed", "done"}:
            return payload
        if status in {"failed", "error"}:
            raise RuntimeError(f"Задача завершилась с ошибкой: {payload}")
        if time.time() > deadline:
            raise TimeoutError(f"Ожидание задачи {task_id} превысило {MAX_WAIT_SEC} сек.")
        time.sleep(POLL_INTERVAL_SEC)

def _ensure_dir(base_out: Optional[Path]) -> Path:
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out = (base_out or Path.cwd() / "outputs") / ts
    out.mkdir(parents=True, exist_ok=True)
    return out

def _save_manifest(out_dir: Path, manifest: Dict[str, Any]) -> None:
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

def _download_to(path: Path, url: str) -> None:
    with requests.get(url, headers=_headers(), stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

def _collect_result_urls(final_payload: Dict[str, Any]) -> List[str]:
    # Унифицируем сбор ссылок на изображения из разных ответов
    # Популярные варианты ключей:
    candidates = []
    data = final_payload.get("data") or final_payload
    if isinstance(data, dict):
        if "results" in data and isinstance(data["results"], list):
            for item in data["results"]:
                if isinstance(item, dict):
                    if "url" in item:
                        candidates.append(item["url"])
                    elif "file_id" in item:
                        candidates.append(("file_id:", item["file_id"]))
        for k in ("image_urls", "images", "urls"):
            if k in data and isinstance(data[k], list):
                candidates.extend(data[k])
        if "url" in data and isinstance(data["url"], str):
            candidates.append(data["url"])
    return candidates

def _resolve_and_download_results(urls_or_ids: List, out_dir: Path) -> List[Path]:
    saved = []
    for i, item in enumerate(urls_or_ids, start=1):
        if isinstance(item, tuple) and item and item[0] == "file_id:":
            file_id = item[1]
            dl = _url(ENDPOINTS["download_file"].format(file_id=file_id))
            out_path = out_dir / f"result_{i:02d}.png"
            _download_to(out_path, dl)
            saved.append(out_path)
        elif isinstance(item, str) and item.startswith("http"):
            out_path = out_dir / f"result_{i:02d}.png"
            _download_to(out_path, item)
            saved.append(out_path)
        else:
            # Если непонятный формат — просто запишем в manifest для ручной дообработки
            pass
    return saved

def run(person_image: Path, cloth_image: Path, out_dir: Optional[Path]) -> Path:
    out = _ensure_dir(out_dir)
    manifest = {"inputs": {"person": str(person_image), "cloth": str(cloth_image)}, "steps": []}

    print("-> Загружаем фото человека...")
    person_ref = upload_file(person_image, "person")
    manifest["steps"].append({"upload_person": person_ref})

    print("-> Загружаем фото одежды...")
    cloth_ref = upload_file(cloth_image, "cloth")
    manifest["steps"].append({"upload_cloth": cloth_ref})

    print("-> Создаем try-on задачу...")
    task_id = create_tryon_task(person_ref, cloth_ref)
    manifest["steps"].append({"task_id": task_id})

    print("-> Ждем завершения задачи...")
    final_payload = wait_for_task(task_id)
    manifest["final_payload"] = final_payload

    print("-> Скачиваем результаты...")
    urls_or_ids = _collect_result_urls(final_payload)
    saved = _resolve_and_download_results(urls_or_ids, out)
    manifest["saved_files"] = [str(p) for p in saved]

    _save_manifest(out, manifest)
    print(f"Готово. Сохранено {len(saved)} файл(ов) в {out}")
    return out

def main():
    p = argparse.ArgumentParser(description="YouCam / Perfect Corp AI Clothes Try-On (demo)")
    p.add_argument("person", type=Path, help="Путь к фото человека (портрет/полный рост)")
    p.add_argument("cloth", type=Path, help="Путь к фото одежды (flat-lay/каталог)")
    p.add_argument("--out-dir", type=Path, default=None, help="Папка вывода (по умолчанию ./outputs/<timestamp>)")
    args = p.parse_args()

    return_code = 0
    try:
        run(args.person, args.cloth, args.out_dir)
    except Exception as e:
        print(f"[ОШИБКА] {e}", file=sys.stderr)
        return_code = 1
    sys.exit(return_code)

if __name__ == "__main__":
    main()
