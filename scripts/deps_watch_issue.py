# -*- coding: utf-8 -*-
"""deps_watch_issue.py — чистая замена секции отчёта в теле постоянного issue.

Никаких сетевых вызовов: workflow сам читает issue через `gh issue view` и
записывает результат через `gh issue edit`. Здесь только маркеры и hash-gating,
чтобы повторный прогон без изменений PyPI не трогал issue и не добавлял коммент.

    python scripts/deps_watch_issue.py --body-file old.md --md-file report.md \
        --fingerprint <sha> > new-body.md
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

START = "<!-- deps-report:start -->"
END = "<!-- deps-report:end -->"
FP_RE = re.compile(r"<!--\s*deps-fingerprint:([0-9a-fA-F]+)\s*-->")


def extract_fingerprint(body: str) -> str:
    m = FP_RE.search(body or "")
    return m.group(1).lower() if m else ""


def fingerprint_changed(body: str, fingerprint: str) -> bool:
    """True, если отчёт изменился (или маркера ещё нет)."""
    return extract_fingerprint(body) != (fingerprint or "").lower()


def replace_report(body: str, markdown: str, fingerprint: str) -> str:
    block = f"{START}\n{markdown.strip()}\n{END}\n<!-- deps-fingerprint:{fingerprint.lower()} -->"
    if START in body and END in body:
        before = body[:body.index(START)].rstrip()
        after = body[body.index(END) + len(END):]
        after = FP_RE.sub("", after).strip()
    else:
        before, after = (body or "").rstrip(), ""
    parts = [p for p in (before, block, after) if p]
    return "\n\n".join(parts) + "\n"


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--body-file", required=True, help="текущее тело issue (может быть пустым)")
    ap.add_argument("--md-file", required=True, help="Markdown-отчёт")
    ap.add_argument("--fingerprint", required=True, help="хеш набора обновлений")
    ap.add_argument("--check", action="store_true", help="только сказать changed/unchanged")
    a = ap.parse_args(argv)

    body = Path(a.body_file).read_text(encoding="utf-8", errors="replace")
    if a.check:
        print("changed" if fingerprint_changed(body, a.fingerprint) else "unchanged")
        return 0
    markdown = Path(a.md_file).read_text(encoding="utf-8", errors="replace")
    sys.stdout.write(replace_report(body, markdown, a.fingerprint))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
