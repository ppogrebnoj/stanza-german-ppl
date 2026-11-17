# -*- coding: utf-8 -*-
"""install_mcp.py — прописать MCP-сервер stanza-german в конфиг клиента.

Пути берутся для текущей машины, поэтому конфиг перестаёт быть ручной правкой
абсолютных путей при каждом переезде. Запись идемпотентна: остальные серверы
в конфиге не трогаются, старая версия файла сохраняется рядом (.bak-*).

Что прописывается:
    command  — python из .venv проекта (если есть), иначе текущий python
    args     — <корень проекта>\\MCP-stanza-german\\server.py
    env      — RULE_ROOT=<корень>\\правило, PYTHONUTF8=1

Запуск:
    python scripts/install_mcp.py --dry-run     # показать, что будет записано
    python scripts/install_mcp.py               # записать в ~/.lmstudio/mcp.json
    python scripts/install_mcp.py --print       # только JSON-фрагмент
    python scripts/install_mcp.py --config <путь к mcp.json>
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _paths as P  # noqa: E402

NAME = "stanza-german"


def default_config_path() -> Path:
    return Path(os.path.expanduser("~")) / ".lmstudio" / "mcp.json"


def client_python() -> str:
    return str(P.venv_python()) if P.venv_python().exists() else sys.executable


def build_entry() -> dict:
    return {
        "command": client_python(),
        "args": [str(P.MCP_DIR / "server.py")],
        "env": {"RULE_ROOT": str(P.RULE_DIR), "PYTHONUTF8": "1"},
    }


def merge(cfg: dict, entry: dict) -> tuple[dict, bool]:
    """Идемпотентный merge: возвращает новый конфиг и признак изменения."""
    new = json.loads(json.dumps(cfg)) if cfg else {}
    servers = new.setdefault("mcpServers", {})
    if servers.get(NAME) == entry:
        return new, False
    servers[NAME] = entry
    return new, True


def main() -> int:
    ap = argparse.ArgumentParser(description="Прописать MCP-сервер stanza-german в конфиг клиента")
    ap.add_argument("--config", default=str(default_config_path()), help="путь к mcp.json клиента")
    ap.add_argument("--dry-run", action="store_true", help="показать результат, ничего не писать")
    ap.add_argument("--print", dest="only_print", action="store_true",
                    help="напечатать только JSON-фрагмент (для других клиентов)")
    a = ap.parse_args()

    if not (P.MCP_DIR / "server.py").exists():
        print(f"ОШИБКА: нет {P.MCP_DIR / 'server.py'}", file=sys.stderr)
        return 1

    entry = build_entry()
    snippet = {"mcpServers": {NAME: entry}}

    if a.only_print:
        print(json.dumps(snippet, ensure_ascii=False, indent=2))
        return 0

    cfg_path = Path(a.config)
    if not cfg_path.exists():
        print(f"конфиг клиента не найден: {cfg_path} — будет создан")
        cfg = {}
    else:
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            print(f"ОШИБКА: {cfg_path} не парсится как JSON: {exc}", file=sys.stderr)
            return 1

    new_cfg, changed = merge(cfg, entry)
    before_servers = set(cfg.get("mcpServers", {}))
    after_servers = set(new_cfg.get("mcpServers", {}))

    print(f"клиент : {cfg_path}")
    print(f"сервер : {NAME}")
    print(f"python : {entry['command']}")
    print(f"server : {entry['args'][0]}")
    print(f"env    : RULE_ROOT={entry['env']['RULE_ROOT']}")

    if not changed:
        print("изменений нет — запись уже актуальна")
        return 0
    if before_servers - {NAME}:
        kept = ", ".join(sorted(before_servers - {NAME}))
        print(f"прочие серверы сохранены: {kept}")
    added = after_servers - before_servers
    if added:
        print(f"новые записи: {', '.join(sorted(added))}")

    if a.dry_run:
        print("\n--dry-run: файл не изменён. Итоговый фрагмент:")
        print(json.dumps(snippet, ensure_ascii=False, indent=2))
        return 0

    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    if cfg_path.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = cfg_path.with_suffix(f".json.bak-{stamp}")
        shutil.copy2(cfg_path, backup)
        print(f"бэкап  : {backup.name}")

    text = json.dumps(new_cfg, ensure_ascii=False, indent=2) + "\n"
    cfg_path.write_text(text, encoding="utf-8", newline="\n")
    print("записано. Перезапустите клиент (LM Studio: Settings -> MCP Servers -> Reload).")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())
