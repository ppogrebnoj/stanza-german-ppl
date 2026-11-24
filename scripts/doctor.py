# -*- coding: utf-8 -*-
"""doctor.py — «машина готова к работе?»: один ответ PASS/FAIL вместо гаданий.

Проверяет ровно то, что ломается при переносе на другую машину:
  * версия Python и версии пакетов против installer/requirements.txt;
  * кэш моделей Stanza (de) — без него не работают стенд, smoke --full и сервер;
  * файлы правила (validator/segment/normalize/config.json) и наборы/разметку;
  * какой RULE_ROOT увидит сервер (env или папка рядом с server.py);
  * git: remote и установленный хук pre-commit.

Запуск:
    python scripts/doctor.py            # человекочитаемо, код возврата 1 при FAIL
    python scripts/doctor.py --json     # машинно (для CI и приёмки)

Ничего не меняет на диске.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _paths as P  # noqa: E402

results = []   # (status, name, detail)
SOFT_MODELS = False   # --soft-models: нет моделей — это WARN, а не FAIL (до распаковки архива)


def add(status: str, name: str, detail: str = "") -> None:
    results.append((status, name, detail))


def ok(name, detail=""):
    add("OK", name, detail)


def warn(name, detail=""):
    add("WARN", name, detail)


def fail(name, detail=""):
    add("FAIL", name, detail)


# ------------------------------------------------------------------ проверки

REQUIRED_MINOR = P.REQUIRED_MINOR       # 3.15 — единственная поддерживаемая версия


def check_python():
    import platform

    v = sys.version_info
    ver = f"{v.major}.{v.minor}.{v.micro}"
    bits = platform.architecture()[0]
    minor = v.minor if v.major == 3 else None
    if minor == REQUIRED_MINOR:
        ok("python", f"{ver} {bits} — эталон проекта (здесь проверены цифры F1)")
    else:
        fail("python", f"{ver} {bits} — нужен Python 3.15; поставить: "
                       f"winget install --id Python.Python.3.15 -e")
    if bits != "64bit":
        fail("python_bits", f"{bits} — нужен x64 (32-bit колёс torch нет)")


def check_pins():
    req = P.REQS
    pins = P.parse_pins(req)
    if not pins:
        fail("requirements", f"не прочитать {req}")
        return
    ok("requirements", req.name)
    hard = {"stanza", "torch", "mcp"}
    for name in sorted(pins):
        want = pins[name]
        have = P.installed_version(name)
        if have is None:
            (fail if name in hard else warn)(f"pkg:{name}", f"не установлен (нужен {want})")
        elif have != want:
            warn(f"pkg:{name}", f"{have} вместо {want}")
        else:
            ok(f"pkg:{name}", have)


def check_models():
    cache = P.stanza_cache_dir()
    models = P.model_dir()
    bad = warn if SOFT_MODELS else fail      # на первом шаге установки моделей ещё нет
    if not cache.exists():
        bad("stanza_cache", f"нет каталога {cache} (модели качает Stanford: .venv\\Scripts\\python.exe -c \"import stanza; stanza.download('de')\")")
        return
    if not (models / "resources.json").exists() and not (cache / "resources.json").exists():
        warn("stanza_cache", f"нет resources.json в {cache}")
    if not models.exists():
        bad("stanza_de", f"нет моделей de в {models} (stanza.download('de') или офлайн: scripts/unpack_models.py --zip <архив>)")
        return
    parts = sorted(p.name for p in models.iterdir() if p.is_dir())
    size = sum(f.stat().st_size for f in models.rglob("*") if f.is_file()) / 2**30
    if not parts and not (models / "default.zip").exists():
        bad("stanza_de", f"каталог {models} пуст")
        return
    ok("stanza_de", f"{size:.2f} ГБ, процессоры: {', '.join(parts) or 'архив'}")
    ok("stanza_cache", str(cache))


def check_rule():
    need = ["validator.py", "segment.py", "normalize.py", "config.json"]
    missing = [f for f in need if not (P.RULE_DIR / f).exists()]
    if missing:
        fail("rule_files", f"нет: {', '.join(missing)} в {P.RULE_DIR}")
    else:
        ok("rule_files", f"{P.RULE_DIR.name}/: {len(need)} файла на месте")
    cfg_path = P.RULE_DIR / "config.json"
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            h = hashlib.sha256(cfg_path.read_bytes()).hexdigest()[:12]
            ok("rule_config", f"version={cfg.get('version')} config_hash={h}")
        except Exception as exc:  # noqa: BLE001
            fail("rule_config", f"config.json не парсится: {exc}")


def check_data():
    for name in ("corpus52.jsonl", "heldout_51.jsonl", "heldout_150.jsonl"):
        path = P.SETS_DIR / name
        if not path.exists():
            fail("data_sets", f"нет {path}")
            continue
        n = sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
        ok("data_sets", f"{name}: {n}")
    for name in ("СПИСОК_150.md", "РАЗМЕТКА_51.md", "РАЗМЕТКА_52.md"):
        if not (P.DATA_DIR / name).exists():
            warn("data_md", f"нет {P.DATA_DIR / name}")


def check_rule_root():
    """Что сервер подхватит как правило: env RULE_ROOT или папка рядом с server.py."""
    env = os.environ.get("RULE_ROOT")
    if env:
        root, src = Path(env), "env RULE_ROOT"
    else:
        root, src = P.MCP_DIR.parent / "правило", "по умолчанию (рядом с server.py)"
    if (root / "validator.py").exists():
        ok("rule_root", f"{root} — {src}")
    else:
        (fail if env else warn)("rule_root", f"{root} — {src}: нет validator.py")


def check_git():
    git_dir = P.ROOT / ".git"
    if not git_dir.exists():
        warn("git", "проект не под git — история не защищена")
        return
    try:
        url = subprocess.run(["git", "-C", str(P.ROOT), "remote", "get-url", "origin"],
                             capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception:
        url = ""
    if url:
        ok("git_remote", url)
    else:
        warn("git_remote", "origin не задан — проект без внешней копии")
    dst = P.hook_dst()
    if not dst.exists():
        warn("git_hook", "pre-commit не установлен (scripts/setup.ps1 поставит)")
    elif b"\r\n" in dst.read_bytes():
        warn("git_hook", f"{dst} с CRLF — переустановите: scripts/setup.ps1")
    else:
        ok("git_hook", str(dst))


def check_venv():
    vp = P.venv_python()
    if vp.exists():
        ok("venv", str(vp))
    else:
        warn("venv", "нет .venv — работа идёт на системном Python (допустимо)")


# ------------------------------------------------------------------ вывод

def main() -> int:
    ap = argparse.ArgumentParser(description="Проверка готовности машины к работе с проектом")
    ap.add_argument("--json", action="store_true", help="машинный вывод")
    ap.add_argument("--soft-models", action="store_true",
                    help="отсутствие моделей Stanza — WARN, не FAIL (шаг установки до распаковки)")
    a = ap.parse_args()
    global SOFT_MODELS
    SOFT_MODELS = a.soft_models

    check_python()
    check_pins()
    check_models()
    check_rule()
    check_data()
    check_rule_root()
    check_git()
    check_venv()

    n_ok = sum(1 for s, _, _ in results if s == "OK")
    n_warn = sum(1 for s, _, _ in results if s == "WARN")
    n_fail = sum(1 for s, _, _ in results if s == "FAIL")

    if a.json:
        print(json.dumps({
            "ok": n_fail == 0,
            "counts": {"OK": n_ok, "WARN": n_warn, "FAIL": n_fail},
            "checks": [{"status": s, "name": n, "detail": d} for s, n, d in results],
        }, ensure_ascii=False, indent=1))
    else:
        for s, n, d in results:
            print(f"  [{s:<4}] {n:<16} {d}")
        print(f"\ndoctor: OK {n_ok}, WARN {n_warn}, FAIL {n_fail}")
        print("ИТОГ: машина готова" if n_fail == 0 else "ИТОГ: есть блокеры (FAIL)")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())
