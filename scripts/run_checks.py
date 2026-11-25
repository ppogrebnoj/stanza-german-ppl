# -*- coding: utf-8 -*-
"""run_checks.py — единая точка запуска Python-проверок installer/lib/checks/.

Только интерфейс: runner не знает бизнес-логику проверок. Он читает manifest,
вызывает нужный скрипт тем же интерпретатором с --json, кладёт результат в envelope
и возвращает код в семантике установщика: 0 OK/SKIP, 1 FAIL, 2 BLOCK,
3 retryable, 4 BROKEN, 5 DELIVERY.

    python scripts/run_checks.py --list
    python scripts/run_checks.py --check doctor --json
    python scripts/run_checks.py --check models --json -- --processors tokenize,pos
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECKS_DIR = ROOT / "installer" / "lib" / "checks"
MANIFEST = CHECKS_DIR / "manifest.json"
EXIT = {"OK": 0, "FAIL": 1, "BLOCK": 2, "RETRY": 3, "BROKEN": 4, "DELIVERY": 5}


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def list_names(manifest: dict | None = None) -> list[str]:
    manifest = manifest or load_manifest()
    return [item["name"] for item in manifest.get("checks", [])]


def find_check(name: str, manifest: dict | None = None) -> dict | None:
    manifest = manifest or load_manifest()
    for item in manifest.get("checks", []):
        if item.get("name") == name:
            return item
    return None


def python_ok() -> bool:
    """Python 3.15 x64 — единственная поддерживаемая среда проверок."""
    return sys.version_info[:2] == (3, 15) and sys.maxsize > 2 ** 32


def first_json(text: str):
    """Достать первый JSON-объект: acceptance печатает вывод подпроцессов до JSON."""
    decoder = json.JSONDecoder()
    for i, ch in enumerate(text or ""):
        if ch == "{":
            try:
                obj, _ = decoder.raw_decode(text[i:])
                return obj
            except json.JSONDecodeError:
                continue
    return None


def envelope(name: str, status: str, code: int, detail: str, data=None, **extra) -> dict:
    report = {
        "schema": 1, "name": name, "status": status, "code": code,
        "exit_code": code, "detail": detail, "data": data or {},
    }
    report.update(extra)
    return report


def map_result(name: str, rc: int, data, stderr: str = "", timed_out: bool = False) -> dict:
    """Свести внутренний rc проверки к коду установщика (без изменения логики проверки)."""
    if timed_out:
        return envelope(name, "FAIL", EXIT["RETRY"], "таймаут проверки", data)
    if rc == 0:
        if not isinstance(data, dict):
            return envelope(name, "BROKEN", EXIT["BROKEN"],
                            "проверка вернула 0, но JSON не прочитан", {"stderr": stderr[-800:]},
                            raw_exit_code=rc)
        ok = bool(data.get("ok", True))
        counts = data.get("counts")
        detail = f"{name}: ok" if ok else f"{name}: not ok"
        if counts:
            detail += " " + json.dumps(counts, ensure_ascii=True)
        return envelope(name, "OK" if ok else "FAIL",
                        EXIT["OK"] if ok else EXIT["FAIL"], detail, data, raw_exit_code=rc)
    if rc == 1:
        return envelope(name, "FAIL", EXIT["FAIL"], f"{name}: FAIL (rc=1)", data, raw_exit_code=rc)
    if rc == 2:
        return envelope(name, "BLOCK", EXIT["BLOCK"], f"{name}: BLOCK (rc=2)", data, raw_exit_code=rc)
    return envelope(name, "BROKEN", EXIT["BROKEN"], f"{name}: неожиданный rc={rc}", data,
                    raw_exit_code=rc)


def run_check(entry: dict, passthrough: list[str]) -> dict:
    name = entry["name"]
    path = CHECKS_DIR / entry["path"]
    if not path.is_file():
        return envelope(name, "DELIVERY", EXIT["DELIVERY"], f"нет файла проверки {entry['path']}")
    cmd = [sys.executable, str(path), "--json"] + list(passthrough)
    try:
        proc = subprocess.run(
            cmd, cwd=str(ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=float(entry.get("timeout_s", 300)),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return map_result(name, 124, None, timed_out=True)
    except OSError as exc:
        return envelope(name, "BROKEN", EXIT["BROKEN"], f"не запустить проверку: {exc}")
    return map_result(name, proc.returncode, first_json(proc.stdout), proc.stderr or "")


def format_report(report: dict, json_mode: bool = False) -> str:
    if json_mode:
        return json.dumps(report, ensure_ascii=True, indent=1)
    return f"{report['status']}:{report['code']} {report['name']} — {report['detail']}"


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    argv = list(argv if argv is not None else sys.argv[1:])
    if "--" in argv:
        base, passthrough = argv[:argv.index("--")], argv[argv.index("--") + 1:]
    else:
        base, passthrough = argv, []

    parser = argparse.ArgumentParser(description="Единая точка запуска проверок installer")
    parser.add_argument("--check", help="имя проверки из installer/lib/checks/manifest.json")
    parser.add_argument("--list", action="store_true", help="список имен проверок")
    parser.add_argument("--json", action="store_true", help="машиночитаемый вывод")
    args = parser.parse_args(base)

    manifest = load_manifest()
    if args.list:
        names = list_names(manifest)
        print(json.dumps(names, ensure_ascii=True) if args.json else "\n".join(names))
        return 0

    if not args.check:
        report = envelope("-", "BROKEN", EXIT["BROKEN"], "укажите --check <name> или --list")
        print(format_report(report, args.json))
        return report["exit_code"]

    entry = find_check(args.check, manifest)
    if not entry:
        report = envelope(args.check, "BROKEN", EXIT["BROKEN"],
                          f"неизвестная проверка {args.check!r}")
        print(format_report(report, args.json))
        return report["exit_code"]
    if not python_ok():
        report = envelope(args.check, "BLOCK", EXIT["BLOCK"],
                          "нужен Python 3.15 x64; текущий интерпретатор не подходит")
        print(format_report(report, args.json))
        return report["exit_code"]

    report = run_check(entry, passthrough)
    print(format_report(report, args.json))
    return report["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
