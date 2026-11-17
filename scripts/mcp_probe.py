# -*- coding: utf-8 -*-
"""mcp_probe.py — проверить MCP-сервер по stdio без MCP-клиента.

Сервер проверяется так же, как его увидит клиент (initialize → tools/list → вызовы), но
не нужен запущенный клиент и его перезапуск. Полезно на новой машине и в CI.

Запуск из корня проекта:
    .venv\\Scripts\\python.exe scripts\\mcp_probe.py
    .venv\\Scripts\\python.exe scripts\\mcp_probe.py --json

Коды выхода: 0 всё в порядке · 1 что-то не так (напечатано что) · 2 в этом python нет пакета mcp.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "MCP-stanza-german" / "server.py"
LOG = ROOT / "MCP-stanza-german" / "server.log"
NEED = {"parse_german", "pipeline_info", "segment_german", "check_segmentation",
        "rule_self_test", "rule_info"}
SENT = "Ich habe bei der Firma gearbeitet."
BLOCKS = ["Ich habe", "bei der Firma gearbeitet."]


async def _checks(s, report: dict, bad: list[str]) -> None:
    """Те же шаги, что делает клиент: handshake, список инструментов, четыре вызова."""
    info = await s.initialize()
    names = sorted(t.name for t in (await s.list_tools()).tools)
    report["server"] = f"{info.serverInfo.name} {info.serverInfo.version}"
    report["tools"] = names
    if not NEED.issubset(names):
        bad.append("нет инструментов: " + ", ".join(sorted(NEED - set(names))))

    d = json.loads((await s.call_tool("pipeline_info", {})).content[0].text)
    report["pipeline"] = {k: d.get(k) for k in ("rule_registered", "offline", "model_dir")}
    report["pipeline"]["torch"] = d.get("versions", {}).get("torch")
    report["pipeline"]["updates"] = d.get("updates", {}).get("available")
    if not d.get("rule_registered"):
        bad.append("правило не подключено: проверь RULE_ROOT в конфиге клиента (УСТАНОВКА.md §1.3, §1.6)")
    if not d.get("offline"):
        bad.append("pipeline не офлайн: модель берётся не из локального кэша")

    g = json.loads((await s.call_tool("rule_self_test", {})).content[0].text)
    report["gate_passed"] = g.get("gate_passed")
    if not g.get("gate_passed"):
        bad.append("rule_self_test: гейт правила не пройден")

    seg = json.loads((await s.call_tool("segment_german", {"text": SENT})).content[0].text)
    report["blocks"] = seg.get("blocks_total")
    report["block_texts"] = (seg.get("sentences") or [{}])[0].get("blocks")
    if seg.get("blocks_total") != 2:
        bad.append(f"segment_german: ожидаем 2 блока, получено {seg.get('blocks_total')}")

    items = json.dumps([{"sentence": SENT, "blocks": BLOCKS}], ensure_ascii=False)
    cs = json.loads((await s.call_tool("check_segmentation", {"items": items})).content[0].text)
    report["judge"] = cs.get("all_compliant")
    if not cs.get("all_compliant"):
        v = (cs.get("results") or [{}])[0].get("violations")
        bad.append("check_segmentation: эталонная разметка не compliant — "
                   + json.dumps(v, ensure_ascii=False))


def _env() -> dict:
    env = dict(os.environ)
    env.update({"RULE_ROOT": str(ROOT / "правило"), "PYTHONUTF8": "1"})
    env.pop("STANZA_RESOURCES_DIR", None)   # кэш Stanza стандартный: временный путь ломает depparse
    return env


def _probe() -> dict:
    """Один запуск сервера как клиента. Никто не обязан выживать: падение = пункт в problems."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    report: dict = {"server": None, "tools": [], "pipeline": {}, "gate_passed": None,
                    "blocks": None, "judge": None}
    bad: list[str] = []
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER)], env=_env())

    async def go() -> None:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as s:
                await _checks(s, report, bad)

    try:
        asyncio.run(go())
    except Exception as e:  # noqa: BLE001
        bad.append(f"сервер не ответил ({type(e).__name__}) — вероятно, умер при старте; "
                   f"смотри {LOG.name} и УСТАНОВКА.md §1.6")
    report["ok"] = not bad
    report["problems"] = bad
    return report


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    try:
        report = _probe()
    except ImportError as e:
        print(f"нет пакета mcp в этом python: {e}\n"
              "нужен интерпретатор из .venv: .venv\\Scripts\\python.exe scripts\\mcp_probe.py")
        return 2

    if "--json" in sys.argv[1:]:
        print(json.dumps(report, ensure_ascii=False, indent=1))
    else:
        print("сервер :", report["server"])
        print("инструменты:", ", ".join(report["tools"]))
        p = report["pipeline"]
        print(f"правило: {p.get('rule_registered')} · офлайн: {p.get('offline')} · "
              f"torch: {p.get('torch')} · обновления: {p.get('updates')}")
        print(f"гейт правила: {report['gate_passed']} · судья: {report['judge']} · "
              f"блоков в пробе: {report['blocks']} · {report.get('block_texts')}")
        for b in report["problems"]:
            print("ПЛОХО:", b)
        print("ИТОГ:", "MCP живой" if report["ok"] else "MCP нездоров")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
