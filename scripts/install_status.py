# -*- coding: utf-8 -*-
"""install_status.py — сводка для человека и агента по install-report.json.

    python scripts/install_status.py [report.json] [--json]

Без аргументов берёт .tmp/install-report.json рядом с проектом. Ничего не меняет.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--json"]
    path = Path(args[0]) if args else ROOT / ".tmp" / "install-report.json"
    if not path.exists():
        print(f"нет отчёта {path}; запустите install.ps1")
        return 2
    report = json.loads(path.read_text(encoding="utf-8"))
    if "--json" in sys.argv[1:]:
        print(json.dumps(report, ensure_ascii=False, indent=1))
        return int(report.get("code", 4))
    print(f"код {report.get('code')}: {report.get('verdict', '')}")
    print(f"режим {report.get('mode')}; Python {report.get('python_path')}; "
          f"модели {report.get('stanza_resources')}")
    for s in report.get("steps", []):
        print(f"  [{s.get('status'):4}] {s.get('id'):12} {s.get('seconds', 0):>6}s {s.get('detail', '')}")
    for b in report.get("blockers", []):
        print(f"  БЛОКЕР {b.get('component')}: {b.get('reason')}; fix: {b.get('fix_cmd')}")
    for f in report.get("failures", []):
        print(f"  СБОЙ {f.get('id')}: {f.get('detail')}; remedy: {f.get('remedy')}")
    na = report.get("next_action") or {}
    if na.get("command"):
        print("next_action.command:", na["command"])
    if na.get("hint"):
        print("next_action:", na["hint"])
    return int(report.get("code", 4))


if __name__ == "__main__":
    raise SystemExit(main())
