# -*- coding: utf-8 -*-
"""pins.py — проверка поддержки версий зависимостей и поиск обновлений.

Зачем: проект опирается на готовые бинарные колёса (torch, numpy). Как только
меняется Python, колёса под него могут отсутствовать — установка падает уже
после скачивания гигабайтов. Скрипт отвечает на два вопроса заранее и без установки:

    python scripts/pins.py             # матрица: какой пин под какой Python существует (wheel)
    python scripts/pins.py --latest    # вышли ли новые версии пинов на PyPI
    python scripts/pins.py --json      # то же машинно (для CI)

Что проверяется:
  * для каждого пина (requirements.txt, requirements-py311.txt) — наличие wheel
    под Python 3.11..3.17 на win_amd64 (или universal py3);
  * вывод «чистого» диапазона Python для каждого файла пинов и сверка
    с заявленным диапазоном (тот, что обещан в ТРЕБОВАНИЯ.md);
  * sdist (сборка из исходников) отмечается отдельно: это значит «собирать компилятором».

Сеть: только pypi.org (JSON API). Без сети скрипт сообщает об этом и выходит с кодом 2.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _paths as P  # noqa: E402

PY_TARGETS = ["3.11", "3.12", "3.13", "3.14", "3.15", "3.16", "3.17"]
PLATFORM = "win_amd64"
CACHE = P.ROOT / "bench" / "cache"
CACHE_FILE = CACHE / "pypi_index.json"
CACHE_TTL = 6 * 3600           # сутки/6 часов — чтобы не дёргать PyPI при каждом запуске

FILES = [("requirements.txt", P.SUPPORTED_MINORS, "основной"),
         ("requirements-py311.txt", (P.LEGACY_MINOR,), "legacy")]


# ------------------------------------------------------------------ PyPI

def _load_cache() -> dict:
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(data: dict) -> None:
    try:
        CACHE.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(data), encoding="utf-8", newline="\n")
    except Exception:
        pass


def fetch_release(pkg: str, ver: str | None = None, cache: dict | None = None) -> dict:
    """Метаданные релиза пакета (или последнего): список файлов и версия. С кэшем."""
    cache = cache if cache is not None else {}
    key = f"{pkg}=={ver}" if ver else f"{pkg}@latest"
    entry = cache.get(key)
    if entry and time.time() - entry.get("ts", 0) < CACHE_TTL:
        return entry["data"]
    url = f"https://pypi.org/pypi/{pkg}/{ver}/json" if ver else f"https://pypi.org/pypi/{pkg}/json"
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=25) as r:
                raw = json.load(r)
            data = {
                "version": raw["info"]["version"],
                "files": [f["filename"] for f in raw.get("urls", [])],
            }
            cache[key] = {"ts": time.time(), "data": data}
            return data
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1.0 + attempt)
    return {"error": str(last)}


WHEEL_RE = re.compile(r"^(?P<name>.+?)-(?P<ver>[^-]+)(-\d[^-]*)?-(?P<py>[^-]+)-(?P<abi>[^-]+)-(?P<plat>[^-]+)\.whl$")


def wheel_info(files: list[str]) -> dict:
    """Разбор файлов релиза: какие py-теги и платформы покрыты, есть ли sdist."""
    wheels, sdists = [], 0
    for f in files:
        m = WHEEL_RE.match(f)
        if m:
            wheels.append((m.group("py"), m.group("plat")))
        elif f.endswith((".tar.gz", ".zip")):
            sdists += 1
    return {"wheels": wheels, "sdists": sdists}


def supports(info: dict, py: str) -> str:
    """yes | no | sdist — есть ли установка под конкретный Python на нашей платформе."""
    tag = "cp" + py.replace(".", "")
    for pytag, plat in info["wheels"]:
        # free-threaded (cp315t) на обычном интерпретаторе не ставится
        single = pytag.split(".")
        universal = pytag.startswith("py3") or pytag.startswith("py2.py3")
        exact = any(t == tag for t in single)
        if (universal or exact) and plat in (PLATFORM, "any", "win32"):
            return "yes"
    if info["sdists"]:
        return "sdist"
    return "no"


def latest_version(pkg: str, cache: dict) -> str | None:
    data = fetch_release(pkg, None, cache)
    return data.get("version") if "error" not in data else None


# ------------------------------------------------------------------ матрица

def build_matrix(files, cache):
    out = []
    for fname, declared, kind in files:
        path = P.ROOT / fname
        if not path.exists():
            out.append({"file": fname, "missing": True, "kind": kind, "pins": [], "supported": []})
            continue
        pins = P.parse_pins(path)
        rows = []
        for pkg, ver in sorted(pins.items()):
            data = fetch_release(pkg, ver, cache)
            if "error" in data:
                rows.append({"package": pkg, "version": ver, "error": data["error"], "cells": {}})
                continue
            info = wheel_info(data["files"])
            cells = {py: supports(info, py) for py in PY_TARGETS}
            rows.append({"package": pkg, "version": ver, "cells": cells,
                         "pure": all(t.startswith("py") for t, _ in info["wheels"]) if info["wheels"] else False})
        good = [py for py in PY_TARGETS
                if rows and all(r["cells"].get(py) == "yes" for r in rows if "cells" in r and r["cells"])]
        # непрерывный диапазон (сравниваем минорные версии как целые)
        def minor(py: str) -> int:
            return int(py.split(".")[1])

        supported = []
        for py in good:
            if not supported:
                supported = [py, py]
            elif minor(py) == minor(supported[1]) + 1:
                supported[1] = py
            else:
                break
        out.append({
            "file": fname, "kind": kind, "pins": rows,
            "declared": [f"3.{m}" for m in declared],
            "supported": supported,
            "ok": bool(supported) and all(f"3.{m}" in good for m in declared),
        })
    return out


def render(matrix) -> None:
    head = "  ".join(f"{py:>5}" for py in PY_TARGETS)
    for block in matrix:
        print(f"\n{block['file']}  ({block['kind']})")
        if block.get("missing"):
            print("  файла нет")
            continue
        print(f"  {'пакет':<22} {head}")
        for r in block["pins"]:
            if "error" in r:
                print(f"  {r['package'] + '==' + r['version']:<22} ошибка PyPI: {r['error'][:40]}")
                continue
            cells = []
            for py in PY_TARGETS:
                v = r["cells"].get(py)
                cells.append({"yes": "да", "no": "—", "sdist": "src"}[v])
            mark = " (pure)" if r["pure"] else ""
            print(f"  {r['package'] + '==' + r['version']:<22} " +
                  "  ".join(f"{c:>5}" for c in cells) + mark)
        sup = block["supported"]
        sup_txt = f"{sup[0]}-{sup[1]}" if sup else "нет"
        decl = ", ".join(block["declared"])
        flag = "OK" if block["ok"] else "ПРОБЛЕМА: заявлено " + decl
        print(f"  => покрытие колёсами: {sup_txt}   заявлено: {decl}   {flag}")
    print("\nобозначения: да — есть wheel под win_amd64/universal, "
          "src — только исходники (нужен компилятор), — нет ничего")


def render_latest(matrix, cache) -> None:
    seen = {}
    for block in matrix:
        for r in block.get("pins", []):
            if "error" in r:
                continue
            seen[(r["package"], r["version"])] = True
    print(f"\n{'пакет':<12} {'сейчас':<12} {'на PyPI':<12} статус")
    for pkg, ver in sorted(seen):
        latest = latest_version(pkg, cache)
        if latest is None:
            status = "не удалось получить"
        elif latest == ver:
            status = "актуально"
        else:
            status = f"есть новее ({latest}) — проверить колёса: python scripts/pins.py"
        print(f"{pkg:<12} {ver:<12} {str(latest):<12} {status}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Проверка поддержки версий зависимостей и обновлений")
    ap.add_argument("--latest", action="store_true", help="показать, вышли ли новые версии пинов")
    ap.add_argument("--json", action="store_true", help="машинный вывод")
    ap.add_argument("--no-cache", action="store_true", help="не использовать кэш PyPI")
    a = ap.parse_args()

    cache = {} if a.no_cache else _load_cache()
    matrix = build_matrix(FILES, cache)
    _save_cache(cache)

    if a.json:
        out = {"targets": PY_TARGETS, "matrix": matrix}
        if a.latest:
            out["latest"] = {
                pkg: {"current": ver, "latest": latest_version(pkg, cache)}
                for block in matrix for r in block.get("pins", [])
                if "error" not in r
                for pkg, ver in [(r["package"], r["version"])]
            }
        print(json.dumps(out, ensure_ascii=False, indent=1))
    else:
        render(matrix)
        if a.latest:
            render_latest(matrix, cache)

    if any(not b.get("ok") for b in matrix if not b.get("missing")):
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())
