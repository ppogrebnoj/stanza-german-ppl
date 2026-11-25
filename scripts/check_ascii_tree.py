# -*- coding: utf-8 -*-
"""check_ascii_tree.py — контракт ASCII-структуры репозитория.

Ловит два класса регрессий:

1) не-ASCII имена в индексе git (и в неисключённых untracked-файлах);
2) известные legacy-упоминания в тексте: старые пути, `-Venv`, LM Studio.

Отдельно проверяет, что на месте остались канонические пути (`rule/`, `data/`, ...).
Bare-упоминания `MARKUP_51.md` и т.п. в Markdown — warning, не блокер.

Только stdlib + git. Свой скрипт, его тесты и фикстуры из контент-скана исключены.
Вывод: stdout, exit 0 — чисто (warning'ы разрешены), 1 — violations, 2 — ошибка.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
EXIT = {"OK": 0, "FAIL": 1, "ERROR": 2}

CANONICAL = (
    "rule/", "data/", "RULE.md", "SPEC.md", "QUESTIONS.md",
    "installer/INSTALL.md", "docs/flags.json",
    "MCP-stanza-german/mcp.json.example",
)

# Локальный мусор и генерируемые артефакты: не мешают разработчику, в CI их нет.
EXCLUDE_DIRS = {
    ".venv", ".tmp", ".stanza", "__pycache__", ".mypy_cache",
    ".ruff_cache", ".pytest_cache", "bench/results",
}
EXCLUDE_SUFFIXES = {".pyc"}

# CHANGELOG — история, контент не сканируем; checker и его тесты содержат denylist.
CONTENT_EXCLUDE_FILES = {
    "CHANGELOG.md",
    "scripts/check_ascii_tree.py",
    "scripts/tests/test_check_ascii_tree.py",
}
CONTENT_EXCLUDE_PREFIXES = ("scripts/tests/fixtures/check_ascii_tree/",)
TEXT_SUFFIXES = {".md", ".py", ".ps1", ".yml", ".yaml", ".json", ".txt"}

LEGACY_PATTERNS = (
    ("legacy_path", re.compile(r"(?:правило|данные)[/\\]", re.IGNORECASE)),
    ("legacy_doc_path", re.compile(
        r"installer[/\\]УСТАНОВКА\.md|docs[/\\]installer-decisions\.md", re.IGNORECASE)),
    ("legacy_flag_venv", re.compile(r"(?<![\w-])-Venv\b|\$Venv\b")),
    ("lm_studio", re.compile(r"LM\s+Studio|\.lmstudio[/\\]mcp\.json", re.IGNORECASE)),
)
BARE_DATA_DOC = re.compile(
    r"(?<![A-Za-z0-9_/\\-])(?:MARKUP_51|MARKUP_52|LIST_150)\.md\b")


def normalize_rel(path: str) -> str:
    """Привести путь к slash-форме, срезав ТОЛЬКО префикс `./`.

    lstrip("./") здесь нельзя: он съедал бы ведущую точку в `.venv/`, `.tmp/`,
    `.github/` и `.gitattributes`, из-за чего исключения не работали.
    """
    rel = str(path).replace("\\", "/")
    while rel.startswith("./"):
        rel = rel[2:]
    return rel


def is_path_excluded(path: str) -> bool:
    rel = normalize_rel(path)
    if rel.startswith("bench/results/"):
        return True
    parts = PurePosixPath(rel).parts
    if any(part in EXCLUDE_DIRS for part in parts):
        return True
    return PurePosixPath(rel).suffix.lower() in EXCLUDE_SUFFIXES


def is_content_excluded(path: str) -> bool:
    rel = normalize_rel(path)
    if is_path_excluded(rel) or rel in CONTENT_EXCLUDE_FILES:
        return True
    if rel.startswith(CONTENT_EXCLUDE_PREFIXES):
        return True
    # mcp.json.example и подобные шаблоны — текст, хотя последний суффикс .example.
    if rel.endswith(".json.example") or rel.endswith(".yml.example"):
        return False
    return PurePosixPath(rel).suffix.lower() not in TEXT_SUFFIXES


def scan_paths(paths) -> list[dict]:
    found = []
    for raw in paths:
        rel = normalize_rel(raw)
        if is_path_excluded(rel):
            continue
        bad = [part for part in PurePosixPath(rel).parts
               if any(ord(ch) > 127 for ch in part)]
        if bad:
            found.append({
                "kind": "non_ascii_path", "path": rel, "line": None,
                "detail": "не-ASCII в компоненте пути: " + ", ".join(bad),
            })
    return found


def check_canonical_paths(root: Path, paths=None) -> list[dict]:
    indexed = set(paths or ())
    found = []
    for item in CANONICAL:
        if item.endswith("/"):
            present = (root / item).is_dir() or any(p.startswith(item) for p in indexed)
        else:
            present = (root / item).exists() or item in indexed
        if not present:
            found.append({
                "kind": "missing_canonical_path", "path": item, "line": None,
                "detail": "канонический путь отсутствует",
            })
    return found


def _line_no(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def scan_content(rel: str, text: str) -> tuple[list[dict], list[dict]]:
    """Вернуть (violations, warnings) для одного текстового файла."""
    violations: list[dict] = []
    warnings: list[dict] = []
    for kind, pattern in LEGACY_PATTERNS:
        for match in pattern.finditer(text):
            violations.append({
                "kind": kind, "path": normalize_rel(rel),
                "line": _line_no(text, match.start()),
                "detail": f"legacy-токен {match.group(0)!r}",
            })
    if normalize_rel(rel).endswith(".md"):
        for match in BARE_DATA_DOC.finditer(text):
            warnings.append({
                "kind": "bare_data_doc", "path": normalize_rel(rel),
                "line": _line_no(text, match.start()),
                "detail": f"{match.group(0)} без префикса data/ — проверьте, это путь или prose",
            })
    return violations, warnings


def collect_paths(root: Path) -> tuple[list[str], str]:
    try:
        proc = subprocess.run(
            ["git", "ls-files", "-co", "--exclude-standard", "-z"],
            cwd=root, capture_output=True, timeout=60, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [], f"не удалось выполнить git ls-files: {exc}"
    if proc.returncode != 0:
        detail = (proc.stderr or b"").decode("utf-8", "replace").strip().replace("\n", " ")
        return [], f"git ls-files rc={proc.returncode}: {detail}"
    return [p for p in proc.stdout.decode("utf-8", "surrogateescape").split("\0") if p], ""


def run_check(root: Path) -> dict:
    paths, error = collect_paths(root)
    if error:
        return {
            "schema": 1, "verdict": "ERROR", "exit_code": EXIT["ERROR"],
            "violations": [], "warnings": [], "error": error,
            "scanned": {"paths": 0, "content_files": 0},
        }

    violations = scan_paths(paths) + check_canonical_paths(root, set(paths))
    warnings: list[dict] = []
    content_files = 0
    for rel in paths:
        if is_content_excluded(rel):
            continue
        path = root / rel
        if not path.is_file():
            continue
        content_files += 1
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            violations.append({
                "kind": "unreadable", "path": normalize_rel(rel), "line": None,
                "detail": f"не читается: {exc}",
            })
            continue
        more_v, more_w = scan_content(rel, text)
        violations.extend(more_v)
        warnings.extend(more_w)

    verdict = "FAIL" if violations else "OK"
    return {
        "schema": 1, "verdict": verdict,
        "exit_code": EXIT[verdict],
        "violations": violations, "warnings": warnings, "error": "",
        "scanned": {"paths": len(paths), "content_files": content_files},
    }


def format_report(report: dict, json_mode: bool = False) -> str:
    if json_mode:
        return json.dumps(report, ensure_ascii=True, indent=1)
    if report["verdict"] == "ERROR":
        return f"ASCII tree ERROR — {report['error']}"
    scanned = report["scanned"]
    lines = [
        f"ASCII tree {report['verdict']} — {scanned['paths']} paths, "
        f"{len(report['violations'])} violations, {len(report['warnings'])} warnings"
    ]
    for item in report["violations"]:
        loc = f":{item['line']}" if item["line"] else ""
        lines.append(f"  VIOLATION [{item['kind']}] {item['path']}{loc}: {item['detail']}")
    for item in report["warnings"]:
        loc = f":{item['line']}" if item["line"] else ""
        lines.append(f"  WARNING   [{item['kind']}] {item['path']}{loc}: {item['detail']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(description="Проверка ASCII-структуры репозитория")
    parser.add_argument("--root", type=Path, default=ROOT, help="корень проекта")
    parser.add_argument("--json", action="store_true", help="машиночитаемый отчёт")
    args = parser.parse_args(argv)
    report = run_check(args.root.resolve())
    print(format_report(report, args.json))
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
