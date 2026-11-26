# -*- coding: utf-8 -*-
"""check_models.py — проверка ресурсов Stanza по манифесту процессоров.

    python scripts/run_checks.py --check models --json
    python scripts/run_checks.py --check models --json -- --processors ... --load

Каталог: STANZA_RESOURCES_DIR, иначе контрактный <root>\\.stanza\\models.
Ничего не скачивает и не меняет: код 0 = ресурсы готовы, 1 = чего-то нет.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[3]   # installer/lib/checks -> корень проекта
DEFAULT_PROCESSORS = "tokenize,mwt,pos,lemma,depparse"


def resource_dir() -> Path:
    env = os.environ.get("STANZA_RESOURCES_DIR")
    if env:
        return Path(env)
    return BASE / ".stanza" / "models"


def manifest_processors(root: Path) -> list[str]:
    """Процессоры из локального resources.json (манифест Stanza), если он есть."""
    for p in (root / "resources.json", root / "de" / "resources.json",
              root.parent / "resources.json"):
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            de = data.get("de", data) if isinstance(data, dict) else {}
            langs = de.get("langs", de) if isinstance(de, dict) else {}
            default = langs.get("default", {}) if isinstance(langs, dict) else {}
            models = default.get("processors", {}) if isinstance(default, dict) else {}
            return sorted(models.keys())
        except Exception:
            continue
    return []


def check_dirs(root: Path, processors: list[str]) -> dict:
    found, missing, sizes = {}, {}, {}
    model_root = root / "de"
    for name in processors:
        d = model_root / name
        if d.is_dir() and any(d.rglob("*.pt")):
            found[name] = str(d)
            sizes[name] = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
        elif d.is_dir() and any(d.iterdir()):
            found[name] = str(d)          # charlm/other formats
            sizes[name] = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
        else:
            missing[name] = str(d)
    return {"found": found, "missing": missing, "sizes": sizes}


def load_pipeline(processors: list[str]) -> dict:
    try:
        import stanza
    except Exception as exc:
        return {"ok": False, "reason": f"нет пакета stanza: {exc}"}
    try:
        # download_method=None запрещает сетевую загрузку: проверяем именно локальный кэш
        pipe = stanza.Pipeline("de", processors=",".join(processors), verbose=False,
                               download_method=None)
        doc = pipe("Ich habe bei der Firma gearbeitet.")
        return {"ok": True, "sentences": len(doc.sentences), "words": sum(len(s.words) for s in doc.sentences)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": str(exc)[:500]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--processors", default=DEFAULT_PROCESSORS)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--load", action="store_true", help="минимальная загрузка pipeline (без сети)")
    a = ap.parse_args()
    processors = [p.strip() for p in a.processors.split(",") if p.strip()]
    root = resource_dir()
    result = {
        "ok": False, "dir": str(root), "processors": processors,
        "manifest_processors": manifest_processors(root),
    }
    result.update(check_dirs(root, processors))
    if a.load and not result["missing"]:
        result["pipeline"] = load_pipeline(processors)
    else:
        result["pipeline"] = {"ok": True, "skipped": True}
    result["ok"] = not result["missing"] and bool(result["pipeline"].get("ok"))
    if a.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
    else:
        print(f"STANZA_RESOURCES_DIR={root}")
        print("есть: " + ", ".join(sorted(result["found"])))
        print("нет:  " + (", ".join(sorted(result["missing"])) or "нет"))
        print("pipeline: " + ("OK" if result["pipeline"].get("ok") else result["pipeline"].get("reason", "FAIL")))
        print("ИТОГ: " + ("готово" if result["ok"] else "ресурсов не хватает"))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    raise SystemExit(main())
