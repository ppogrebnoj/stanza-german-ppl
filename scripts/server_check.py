# -*- coding: utf-8 -*-
"""server_check.py — диагностика MCP-сервера без запуска MCP-клиента.

Проверяет: файл сервера, набор инструментов (AST, без импорта torch), доступность
правила по RULE_ROOT (сервер сам определяет путь), каталог моделей и пакет mcp.
В ответе всегда есть rule_status — та же строка, что сервер пишет в журнал при старте.
Ничего не меняет; код 0 = сервер может стартовать.
"""
from __future__ import annotations

import ast
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "MCP-stanza-german" / "server.py"
NEED = {"parse_german", "pipeline_info", "segment_german", "check_segmentation",
        "rule_self_test", "rule_info"}
LOG = ROOT / "MCP-stanza-german" / "server.log"


def tools_from_ast() -> list[str]:
    if not SERVER.exists():
        return []
    try:
        tree = ast.parse(SERVER.read_text(encoding="utf-8"))
    except Exception:
        return []
    names = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call):
                continue
            fn = dec.func
            label = fn.attr if isinstance(fn, ast.Attribute) else (fn.id if isinstance(fn, ast.Name) else "")
            if label not in ("_async_tool", "tool"):
                continue
            arg = dec.args[0] if dec.args else None
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                names.append(arg.value)
    return sorted(set(names))


def rule_status() -> tuple[bool, str]:
    root = Path(os.environ.get("RULE_ROOT") or str(ROOT / "правило"))
    cfg = root / "config.json"
    validator = root / "validator.py"
    if not validator.exists():
        msg = f"rule not connected: нет validator.py; RULE_ROOT={root}"
        _log(msg)
        return False, msg
    if not cfg.exists():
        msg = f"rule error: нет config.json; RULE_ROOT={root}"
        _log(msg)
        return False, msg
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
        import hashlib
        h = hashlib.sha256(cfg.read_bytes()).hexdigest()[:12]
        return True, f"rule {data.get('_version', '?')}, config_hash={h}, RULE_ROOT={root}"
    except Exception as exc:  # noqa: BLE001
        msg = f"rule error: {exc}; RULE_ROOT={root}"
        _log(msg)
        return False, msg


def _log(msg: str) -> None:
    try:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(f"{msg}\n")
    except Exception:
        pass


def main() -> int:
    tools = tools_from_ast()
    rule_ok, status = rule_status()
    models = Path(os.environ.get("STANZA_RESOURCES_DIR") or (ROOT / ".stanza" / "models"))
    try:
        import mcp  # noqa: F401
        mcp_ok = True
    except Exception:
        mcp_ok = False
    problems = []
    if not SERVER.exists():
        problems.append("нет server.py")
    if not NEED.issubset(tools):
        problems.append("нет инструментов: " + ", ".join(sorted(NEED - set(tools))))
    if not rule_ok:
        problems.append(status)
    if not mcp_ok:
        problems.append("нет пакета mcp в этом python")
    result = {
        "ok": not problems, "server": str(SERVER), "tools": tools,
        "rule_status": status, "rule_root": str(Path(os.environ.get("RULE_ROOT") or (ROOT / "правило"))),
        "stanza_resources": str(models), "models_dir_exists": models.exists(),
        "mcp_import": mcp_ok, "problems": problems,
    }
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
