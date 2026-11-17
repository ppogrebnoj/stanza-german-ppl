# -*- coding: utf-8 -*-
"""Общие пути проекта для скриптов развёртывания (scripts/*.py).

Правило и сервер этот модуль не используют: у них своя логика (правило — только
stdlib + Stanza, сервер — RULE_ROOT). Здесь — то, что нужно установке и проверке
окружения.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # корень проекта
RULE_DIR = ROOT / "правило"
MCP_DIR = ROOT / "MCP-stanza-german"
SETS_DIR = ROOT / "bench" / "sets"
DATA_DIR = ROOT / "данные"
REQS = ROOT / "requirements.txt"          # основной набор (последние версии), Python 3.12-3.15
REQS_PY311 = ROOT / "requirements-py311.txt"   # legacy для 3.11: у numpy 2.5.x нет колёс под cp311
LOCK = ROOT / "requirements.lock"

STANZA_VERSION = "1.15.0"     # версия, под которую снят кэш моделей
LANG = "de"


def _fallback_cache_dir() -> Path:
    """Стандартный каталог Stanza, если сам stanza не импортируется."""
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
        return base / "StanfordNLP" / "stanza" / "Cache" / STANZA_VERSION / "resources"
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "StanfordNLP"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache"))
        return base / "stanfordnlp" / "stanza" / "Cache" / STANZA_VERSION / "resources"
    return base / "stanza" / "Cache" / STANZA_VERSION / "resources"


def stanza_cache_dir() -> Path:
    """Каталог кэша моделей: STANZA_RESOURCES_DIR, иначе — дефолт самого Stanza."""
    env = os.environ.get("STANZA_RESOURCES_DIR")
    if env:
        return Path(env)
    try:                                   # точный путь знает установленный stanza
        from stanza.resources.common import DEFAULT_MODEL_DIR
        return Path(DEFAULT_MODEL_DIR)
    except Exception:                      # stanza нет — считаем по платформе
        return _fallback_cache_dir()


def model_dir() -> Path:
    """Каталог моделей одного языка (de)."""
    return stanza_cache_dir() / LANG


def venv_dir() -> Path:
    return ROOT / ".venv"


def venv_python() -> Path:
    return venv_dir() / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def hook_src() -> Path:
    return RULE_DIR / "git-hooks" / "pre-commit"


def hook_dst() -> Path:
    return ROOT / ".git" / "hooks" / "pre-commit"


BASELINE_MINOR = 15                      # отправная точка: 3.15 (здесь сняты цифры F1)
SUPPORTED_MINORS = (12, 13, 14, 15)     # основной набор
LEGACY_MINOR = 11                       # старый набор (torch 2.14.0 / numpy 2.4.6)


def requirements_path() -> Path:
    """Файл пинов под текущий интерпретатор.

    3.12-3.15 — основной набор (последние версии зависимостей).
    3.11 — legacy: numpy 2.5.x не имеет колёс под cp311.
    """
    if sys.version_info[:2] == (3, LEGACY_MINOR) and REQS_PY311.exists():
        return REQS_PY311
    return REQS


def parse_pins(path: Path | None = None) -> dict:
    """Пины прямых зависимостей (по умолчанию — файл под текущий Python)."""
    path = path or requirements_path()
    import re

    pins = {}
    if path is None or not path.exists():
        return pins
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        m = re.match(r"([A-Za-z0-9_.\-]+)==([^\s;]+)", line)
        if m:
            pins[m.group(1)] = m.group(2)
    return pins


def installed_version(name: str):
    """Версия установленного пакета без локальной части (+cpu) или None."""
    try:
        from importlib.metadata import version
        return version(name).split("+", 1)[0]
    except Exception:
        return None
