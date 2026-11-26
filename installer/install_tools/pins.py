# -*- coding: utf-8 -*-
"""pins.py — проверка поддержки версий зависимостей и поиск обновлений.

Зачем: проект опирается на готовые бинарные колёса (torch, numpy). Как только
меняется Python, колёса под него могут отсутствовать — установка падает уже
после скачивания гигабайтов. Скрипт отвечает на два вопроса заранее и без установки:

    python installer/install_tools/pins.py             # матрица колёс по версиям Python
    python installer/install_tools/pins.py --latest    # обновления на PyPI (для человека)
    python installer/install_tools/pins.py --write bench/results/deps.json   # ТОЛЬКО вручную
    python installer/install_tools/pins.py --report --out-md /tmp/a.md --out-json /tmp/a.json
                                                       # info-режим: ничего не пишет в репозиторий

Что проверяется:
  * для каждого пина (requirements.txt) — наличие wheel под Python 3.15..3.17
    на win_amd64 (или universal py3);
  * вывод «чистого» диапазона Python для каждого файла пинов и сверка
    с требуемой версией Python (3.15 — эталон, см. INSTALL.md);
  * sdist (сборка из исходников) отмечается отдельно: это значит «собирать компилятором».

Сеть: только pypi.org (JSON API). Без сети скрипт сообщает об этом и выходит с кодом 2.

Снимок (--write): файл вида {as_of, python, packages:{пин/последняя}, models:{stanza, pack_ok}} —
его читает MCP-сервер в pipeline_info().updates. Снимок = только факты, без оценок и вердиктов.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import _paths as P  # noqa: E402

PY_TARGETS = ["3.15", "3.16", "3.17"]     # 3.15 — эталон; остальные — на будущее
PLATFORM = "win_amd64"
CACHE = P.ROOT / "bench" / "cache"
CACHE_FILE = CACHE / "pypi_index.json"
CACHE_TTL = 6 * 3600           # сутки/6 часов — чтобы не дёргать PyPI при каждом запуске
_PYPI_DEAD = {"until": 0.0}    # после первого сбоя: не ползать по сети за каждым пакетом

FILES = [(str(P.REQS.relative_to(P.ROOT)), (P.REQUIRED_MINOR,), "пины проекта")]
SNAPSHOT_DEFAULT = P.ROOT / "bench" / "results" / "deps.json"
LOCK_NAME = str(P.LOCK.relative_to(P.ROOT))
REPORT_ISSUE_TITLE = "📦 Обновления зависимостей — только информация"
STALE_DAYS = 14


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
    if time.time() < _PYPI_DEAD["until"]:
        # сеть уже легла: не дёргать её по разу на каждый пакет (иначе офлайн = минуты ожидания)
        return {"error": "PyPI недоступен (сеть не отвечает, кэш пуст)"}
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
            _PYPI_DEAD["until"] = 0.0
            return data
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1.0 + attempt)
    _PYPI_DEAD["until"] = time.time() + 1800
    return {"error": str(last)}


WHEEL_RE = re.compile(r"^(?P<name>.+?)-(?P<ver>[^-]+)(-\d[^-]*)?-(?P<py>[^-]+)-(?P<abi>[^-]+)-(?P<plat>[^-]+)\.whl$")


def wheel_info(files: list[str]) -> dict:
    """Разбор файлов релиза: какие py-теги и платформы покрыты, есть ли sdist."""
    wheels, sdists = [], 0
    for f in files:
        m = WHEEL_RE.match(f)
        if m:
            wheels.append((m.group("py"), m.group("abi"), m.group("plat")))
        elif f.endswith((".tar.gz", ".zip")):
            sdists += 1
    return {"wheels": wheels, "sdists": sdists}


def supports(info: dict, py: str) -> str:
    """yes | no | sdist — есть ли установка под конкретный Python на нашей платформе."""
    tag = "cp" + py.replace(".", "")
    minor = int(py.split(".")[1])
    for pytag, abi, plat in info["wheels"]:
        if plat not in (PLATFORM, "any", "win32"):
            continue
        # pure-python и cpXY-abi3 (stable ABI) ставятся на более новые версии;
        # free-threaded cp314t/cp315t на обычном интерпретаторе не ставится.
        universal = pytag.startswith("py3") or pytag.startswith("py2.py3")
        exact = pytag == tag and "t" not in abi
        stable_abi = False
        m = re.match(r"^cp(\d)(\d+)$", pytag)     # cp38 -> 3.8, cp311 -> 3.11
        if (abi == "abi3" or abi.startswith("abi3.")) and m:
            base_major, base_minor = int(m.group(1)), int(m.group(2))
            stable_abi = base_major == 3 and 8 <= base_minor <= minor
        if universal or exact or stable_abi:
            return "yes"
    if info["sdists"]:
        return "sdist"
    return "no"


def latest_version(pkg: str, cache: dict) -> str | None:
    data = fetch_release(pkg, None, cache)
    return data.get("version") if "error" not in data else None


# ------------------------------------------------------------------ снимок для сервера

def build_snapshot(cache: dict) -> dict:
    """Только факты: пин, последняя версия на PyPI, версия python, есть ли набор моделей de."""
    pins = P.parse_pins()
    pkgs = {}
    for pkg, ver in sorted(pins.items()):
        latest = latest_version(pkg, cache)
        if latest:
            pkgs[pkg] = {"current": ver, "latest": latest}
    models = {"stanza": P.installed_version("stanza") or pins.get("stanza"),
              "pack_ok": (P.model_dir() / "depparse").exists()}
    return {
        "as_of": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "python": "%d.%d" % sys.version_info[:2],
        "packages": pkgs,
        "models": models,
    }


def write_snapshot(path: Path, snapshot: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


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
                         "pure": all(t.startswith("py") for t, _, _ in info["wheels"]) if info["wheels"] else False})
        known = [r for r in rows if r.get("cells")]   # пустые cells = нет данных PyPI
        good = [py for py in PY_TARGETS
                if known and all(r["cells"].get(py) == "yes" for r in known)]
        # Нет данных PyPI — это НЕ провал контракта колёс, а состояние «нет данных».
        status = "unknown" if not known else (
            "ok" if bool(good) and all(f"3.{m}" in good for m in declared) else "fail")
        # строка без cells = нет данных PyPI: покрытие не считается «зелёным»
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
            "status": status,
            "ok": True if status == "unknown" else (status == "ok"),
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
        status = block.get("status", "ok" if block["ok"] else "fail")
        flag = {"ok": "OK", "unknown": "НЕТ ДАННЫХ PyPI",
                "fail": "ПРОБЛЕМА: заявлено " + decl}[status]
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
            status = f"есть новее ({latest}) — проверить колёса: python installer/install_tools/pins.py"
        print(f"{pkg:<12} {ver:<12} {str(latest):<12} {status}")


# ------------------------------------------------------------------ отчёт (только чтение)

def report_fingerprint(rows: list[dict]) -> str:
    """Хеш набора обновлений: as_of и ссылка на run НЕ влияют на хеш."""
    payload = [{"package": r["package"], "current": r["current"],
                "latest": r.get("latest"), "wheel": r.get("wheel_315")}
               for r in sorted(rows, key=lambda x: x["package"])]
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
    ).hexdigest()[:12]


def build_report(cache: dict, run_url: str = "") -> dict:
    """Report-only: все 62 позиций lock, PyPI latest и отдельный wheel-контракт 3.15."""
    lock = P.parse_pins(P.LOCK)              # 62 позиции
    direct = P.parse_pins()                  # прямые пины requirements.txt
    matrix = build_matrix(
        FILES + [(LOCK_NAME, (P.REQUIRED_MINOR,), "замок зависимостей")], cache)
    lock_block = next((b for b in matrix if b["file"] == LOCK_NAME), {"pins": []})
    wheel_by_pkg = {
        r["package"]: (r["cells"].get(f"3.{P.REQUIRED_MINOR}", "unknown")
                        if "cells" in r else "unknown")
        for r in lock_block.get("pins", [])
    }
    rows = []
    for pkg, ver in sorted(lock.items()):
        data = fetch_release(pkg, None, cache)
        latest = data.get("version") if "error" not in data else None
        status = "нет данных" if latest is None else ("актуально" if latest == ver else "есть новее")
        rows.append({"package": pkg, "current": ver, "latest": latest,
                     "wheel_315": wheel_by_pkg.get(pkg, "unknown"), "status": status})
    return {
        "as_of": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "run_url": run_url,
        "pypi_available": any(r["latest"] for r in rows),
        "lock": LOCK_NAME, "direct_pins": direct,
        "packages": rows, "fingerprint": report_fingerprint(rows),
        "wheel_contract": {
            "status": lock_block.get("status", "unknown"),
            "python": f"3.{P.REQUIRED_MINOR}", "platform": PLATFORM,
        },
        "schedule_note": ("Scheduled-запуски GitHub могут задерживаться и отключаться после "
                          "60 дней без активности репозитория; выход — workflow_dispatch."),
    }


def report_markdown(report: dict) -> str:
    wc = report["wheel_contract"]
    status = {"ok": "OK", "unknown": "нет данных", "fail": "ПРОБЛЕМА"}.get(wc["status"], wc["status"])
    head = [
        "### 📦 Обновления зависимостей — только информация",
        "",
        f"as_of: `{report['as_of']}` · позиций lock: **{len(report['packages'])}** · "
        f"wheel-контракт Python {wc['python']} {wc['platform']}: **{status}**",
    ]
    if report.get("run_url"):
        head.append(f"источник: [run {report['run_url']}]({report['run_url']})")
    if not report["pypi_available"]:
        head.append("")
        head.append("**PyPI недоступен** — данные о новых версиях отсутствуют (нет данных); job не провален.")
    head += [
        "",
        "| пакет | current | latest | wheel 3.15 | статус |",
        "|---|---|---|---|---|",
    ]
    for r in report["packages"]:
        head.append("| {package} | {current} | {latest} | {wheel} | {status} |".format(
            package=r["package"], current=r["current"],
            latest=r["latest"] or "нет данных", wheel=r["wheel_315"], status=r["status"]))
    head += [
        "",
        f"Прямые пины: {', '.join(sorted(report['direct_pins']))}.",
        "",
        "> " + report["schedule_note"],
        "> Решение об обновлении принимается вручную: отчёт не меняет `requirements.lock`, ",
        "> `requirements.txt` и `bench/results/deps.json`.",
    ]
    return "\n".join(head)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Проверка поддержки версий зависимостей и обновлений")
    ap.add_argument("--latest", action="store_true", help="показать, вышли ли новые версии пинов")
    ap.add_argument("--json", action="store_true", help="машинный вывод")
    ap.add_argument("--no-cache", action="store_true", help="не использовать кэш PyPI")
    ap.add_argument("--write", metavar="ФАЙЛ", nargs="?", const=str(SNAPSHOT_DEFAULT), default="",
                    help="ВРУЧНУЮ записать снимок обновлений (по умолчанию bench/results/deps.json)")
    ap.add_argument("--report", action="store_true",
                    help="report-only: Markdown + JSON, без записи в репозиторий")
    ap.add_argument("--out-md", default="", help="куда записать Markdown (вне репозитория)")
    ap.add_argument("--out-json", default="", help="куда записать JSON (вне репозитория)")
    ap.add_argument("--run-url", default="", help="ссылка на run для отчёта")
    a = ap.parse_args(argv)
    if a.report and a.write:
        ap.error("--report и --write несовместимы: отчёт ничего не пишет в репозиторий")

    cache = {} if a.no_cache else _load_cache()

    if a.report:
        report = build_report(cache, a.run_url)
        md = report_markdown(report)
        as_json = json.dumps(report, ensure_ascii=False, indent=1) + "\n"
        # Только явные пути ВНЕ репозитория; кэш PyPI и снимок в info-режиме не пишутся.
        if a.out_md:
            Path(a.out_md).write_text(md, encoding="utf-8", newline="\n")
        if a.out_json:
            Path(a.out_json).write_text(as_json, encoding="utf-8", newline="\n")
        if not a.out_md:
            print(md)
        if a.json and not a.out_json:
            print(as_json)
        if not report["pypi_available"]:
            print("::warning::PyPI недоступен — в отчёте 'нет данных'; job не провален",
                  file=sys.stderr)
        return 1 if report["wheel_contract"]["status"] == "fail" else 0

    matrix = build_matrix(FILES, cache)
    _save_cache(cache)
    snap_rc = 0
    if a.write:
        snap = build_snapshot(cache)
        if not snap["packages"]:
            print("нет данных PyPI (офлайн?) — снимок не записан", file=sys.stderr)
            snap_rc = 2
        else:
            write_snapshot(Path(a.write), snap)
            print(f"снимок записан: {a.write}  пакетов {len(snap['packages'])}  as_of {snap['as_of']}")

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

    if any(b.get("ok") is False for b in matrix if not b.get("missing")):
        return 1
    if any(b.get("status") == "unknown" for b in matrix if not b.get("missing")):
        print("::warning::PyPI недоступен — покрытие колёсами не проверено", file=sys.stderr)
    return snap_rc


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())
