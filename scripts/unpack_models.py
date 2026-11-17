# -*- coding: utf-8 -*-
"""unpack_models.py — развернуть архив моделей Stanza на этой машине.

Дополняет pack_models.py: качает (или берёт локальный) архив, проверяет
контрольную сумму, безопасно распаковывает в каталог кэша Stanza и — по флагу
--check — сразу проверяет, что пайплайн и правило работают.

Запуск:
    python scripts/unpack_models.py --release models-v1        # скачать ассет через gh и развернуть
    python scripts/unpack_models.py --zip stanza-models-de-1.15.0.zip
    python scripts/unpack_models.py --zip ... --dest D:\\stanza-models   # нестандартный каталог
    python scripts/unpack_models.py --zip ... --check          # + проверка правила 52/52

Если каталог не стандартный, скрипт напечатает переменную STANZA_RESOURCES_DIR,
которую нужно прописать серверу (mcp.json) и doctor.py.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _paths as P  # noqa: E402


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve_zip(args) -> Path:
    if args.zip:
        p = Path(args.zip)
        if not p.exists():
            raise SystemExit(f"ОШИБКА: нет файла {p}")
        return p
    if not args.release:
        raise SystemExit("укажите --zip <файл> или --release <тег>")
    tmp = Path(tempfile.mkdtemp(prefix="stanza-models-"))
    print(f"качаю ассет {args.release} через gh -> {tmp}")
    cmd = ["gh", "release", "download", args.release, "-D", str(tmp)]
    if args.pattern:
        cmd += ["-p", args.pattern]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"ОШИБКА gh: {r.stderr.strip() or r.stdout.strip()}")
    zips = sorted(tmp.glob("*.zip"))
    if not zips:
        raise SystemExit(f"ОШИБКА: в релизе {args.release} нет .zip")
    return zips[0]


def verify(zip_path: Path, expected: str | None, skip: bool) -> None:
    if skip:
        print("проверка суммы пропущена (--skip-verify)")
        return
    want = expected
    if not want:
        sum_file = zip_path.with_suffix(zip_path.suffix + ".sha256")
        if sum_file.exists():
            want = sum_file.read_text(encoding="utf-8").split()[0].strip()
        else:
            print("ВНИМАНИЕ: рядом нет .sha256 — проверка невозможна, продолжаю")
            return
    have = sha256_of(zip_path)
    if have != want:
        raise SystemExit(f"ОШИБКА: sha256 не совпал\n  ждали {want}\n  получили {have}")
    print(f"sha256 ok: {have[:16]}…")


def safe_members(zf: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    out = []
    for info in zf.infolist():
        name = info.filename
        if name.startswith("/") or name.startswith("\\") or ":" in name.split("/")[0] \
                or ".." in Path(name).parts:
            raise SystemExit(f"ОШИБКА: небезопасный путь в архиве: {name}")
        out.append(info)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Развернуть архив моделей Stanza")
    ap.add_argument("--zip", help="локальный архив")
    ap.add_argument("--release", help="тег GitHub Releases (скачать через gh)")
    ap.add_argument("--pattern", default="stanza-models-*.zip", help="шаблон ассета в релизе")
    ap.add_argument("--dest", default="", help="каталог назначения (по умолчанию кэш Stanza)")
    ap.add_argument("--sha256", default="", help="ожидаемая контрольная сумма")
    ap.add_argument("--skip-verify", action="store_true", help="не проверять sha256")
    ap.add_argument("--force", action="store_true", help="перезаписать существующие файлы")
    ap.add_argument("--check", action="store_true", help="проверить правило на corpus52 после распаковки")
    a = ap.parse_args()

    zip_path = resolve_zip(a)
    verify(zip_path, a.sha256 or None, a.skip_verify)

    dest = Path(a.dest) if a.dest else P.stanza_cache_dir()
    dest.mkdir(parents=True, exist_ok=True)
    print(f"распаковка -> {dest}")

    with zipfile.ZipFile(zip_path) as zf:
        members = safe_members(zf)
        written = skipped = 0
        for info in members:
            target = dest / info.filename
            if target.exists() and not a.force:
                skipped += 1
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if info.is_dir():
                continue
            with zf.open(info) as src, target.open("wb") as dst:
                for chunk in iter(lambda: src.read(8 << 20), b""):
                    dst.write(chunk)
            written += 1
    print(f"записано файлов: {written}, пропущено существующих: {skipped}")

    need = dest / P.LANG / "depparse"
    if not need.exists():
        raise SystemExit(f"ОШИБКА: после распаковки нет {need} — архив не тот?")
    reg = dest / "resources.json"
    if not reg.exists():
        print("ВНИМАНИЕ: нет resources.json — Stanza может не увидеть модели")

    default = P.stanza_cache_dir()
    if dest.resolve() != default.resolve():
        print("\nкаталог нестандартный — пропишите его как переменную окружения:")
        print(f"  STANZA_RESOURCES_DIR={dest}")
        print("  (в mcp.json -> env сервера stanza-german, и для doctor/smoke)")

    if a.check:
        sets = P.SETS_DIR / "corpus52.jsonl"
        if not sets.exists():
            print("набора bench/sets/corpus52.jsonl нет — проверка пропущена")
        else:
            env = dict(os.environ, STANZA_RESOURCES_DIR=str(dest), PYTHONUTF8="1")
            print("\nпроверка: validator на corpus52")
            r = subprocess.run([sys.executable, str(P.RULE_DIR / "validator.py"),
                                "--set", str(sets)], env=env, capture_output=True, text=True)
            tail = (r.stdout or r.stderr).strip().splitlines()[-3:]
            for line in tail:
                print("  " + line)
            if "compliant 52" not in (r.stdout or ""):
                raise SystemExit("ОШИБКА: проверка не дала compliant 52")
            print("  модели рабочие: правило 52/52")
    else:
        print("\nпроверка моделей не запрошена (--check)")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())
