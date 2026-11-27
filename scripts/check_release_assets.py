# -*- coding: utf-8 -*-
"""Проверка: one-liner из README указывает на актуальные ассеты релиза.

Ловит корневую причину ручного прогона 27.11.2026: `releases/latest` --
старый тег v4.0.5, в bootstrap ещё нет standalone-доставки flags, а
source.zip собран до PR #15-#30. Проверяет через GitHub API (gh):

1. `bootstrap.ps1.sha256` совпадает с локальным `bootstrap.ps1`;
2. latest release == версия из MCP-stanza-german/version.json;
3. ассет `bootstrap.ps1` в релизе имеет тот же SHA256, что и в master;
4. digest ассета `bootstrap.ps1.sha256` совпадает с локальным файлом;
5. `bootstrap.ps1` в теге релиза совпадает с master;
6. ассет `stanza-german-ppl-source.zip` присутствует.

Выход: 0 -- всё совпадает, 1 -- рассинхрон (нужно опубликовать
новый релиз из master), 2 -- нет gh/сети/ошибка API.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_JSON = ROOT / "MCP-stanza-german" / "version.json"


def gh_json(args: list[str], attempts: int = 3) -> dict:
    """gh api -> JSON, с небольшими ретраями на сетевые обрывы."""
    last = ""
    for i in range(attempts):
        p = subprocess.run(["gh", "api", *args], capture_output=True, text=True)
        if p.returncode == 0:
            try:
                return json.loads(p.stdout)
            except json.JSONDecodeError as exc:
                last = f"bad JSON: {exc}"
        else:
            last = (p.stderr or p.stdout).strip().splitlines()[-1] if (p.stderr or p.stdout) else "gh failed"
        if i + 1 < attempts:
            time.sleep(2)
    raise RuntimeError(last)


def gh_text(args: list[str], attempts: int = 3) -> str:
    """gh api -> чистый текст (для --jq '.content', где строка не в JSON)."""
    last = ""
    for i in range(attempts):
        p = subprocess.run(["gh", "api", *args], capture_output=True, text=True)
        if p.returncode == 0:
            return p.stdout
        last = (p.stderr or p.stdout).strip().splitlines()[-1]
        if i + 1 < attempts:
            time.sleep(2)
    raise RuntimeError(last)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def repo_slug() -> str:
    p = subprocess.run(["git", "-C", str(ROOT), "remote", "get-url", "origin"],
                       capture_output=True, text=True)
    url = p.stdout.strip() if p.returncode == 0 else ""
    m = re.search(r"github\.com[:/](.+?)(?:\.git)?$", url)
    if m:
        return m.group(1)
    return "ppogrebnoj/stanza-german-ppl"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", default=None, help="owner/repo; по умолчанию из git remote origin")
    ap.add_argument("--json", action="store_true", help="машинный вывод")
    args = ap.parse_args()

    results: list[tuple[bool, str, str]] = []

    def check(ok: bool, name: str, detail: str = "") -> None:
        results.append((bool(ok), name, detail))

    version = json.loads(VERSION_JSON.read_text(encoding="utf-8"))["server_version"]
    expected_tag = f"v{version}"
    local_boot = (ROOT / "bootstrap.ps1").read_bytes()
    local_hash = sha256(local_boot)
    sha_file = (ROOT / "bootstrap.ps1.sha256").read_text(encoding="utf-8")
    want_in_file = sha_file.split()[0].lower()

    check(local_hash == want_in_file, "local bootstrap hash == bootstrap.ps1.sha256",
          f"file={want_in_file} local={local_hash}")

    repo = args.repo or repo_slug()
    try:
        release = gh_json([f"repos/{repo}/releases/latest",
                           "--jq", "{tag:.tag_name, assets:[.assets[]|{name,digest,id}]}"])
        tag = release.get("tag", "")
        assets = {a["name"]: a for a in release.get("assets", [])}
    except Exception as exc:  # gh/сеть
        print(f"ERROR: gh api: {exc}", file=sys.stderr)
        return 2

    check(tag == expected_tag, "latest release == version.json",
          f"latest={tag} expected={expected_tag}")

    rel_boot = assets.get("bootstrap.ps1", {})
    digest = (rel_boot.get("digest") or "").lower()
    check(digest == f"sha256:{local_hash}", "release bootstrap.ps1 digest == master",
          f"release={digest or 'н/д'} master=sha256:{local_hash}")

    sha_asset = assets.get("bootstrap.ps1.sha256")
    if sha_asset:
        expected_sha_digest = f"sha256:{sha256((ROOT / 'bootstrap.ps1.sha256').read_bytes())}"
        actual_sha_digest = (sha_asset.get("digest") or "").lower()
        check(actual_sha_digest == expected_sha_digest,
              "release bootstrap.ps1.sha256 digest == master",
              f"release={actual_sha_digest or 'н/д'} master={expected_sha_digest}")
    else:
        check(False, "release bootstrap.ps1.sha256 asset exists", "ассет отсутствует")

    check("stanza-german-ppl-source.zip" in assets, "source.zip asset exists")

    try:
        encoded = gh_text([f"repos/{repo}/contents/bootstrap.ps1?ref={tag}", "--jq", ".content"])
        tagged_hash = sha256(base64.b64decode("".join(encoded.split())))
    except Exception as exc:
        tagged_hash = f"ERROR: {exc}"
    check(tagged_hash == local_hash, f"bootstrap.ps1 in tag {tag} == master",
          f"tag={tagged_hash} master={local_hash}")

    ok = sum(1 for good, _, _ in results if good)
    if args.json:
        print(json.dumps({"ok": ok == len(results), "passed": ok, "total": len(results),
                          "expected_tag": expected_tag, "latest_tag": tag,
                          "checks": [{"ok": g, "name": n, "detail": d} for g, n, d in results]},
                         ensure_ascii=False, indent=2))
    else:
        for good, name, detail in results:
            print(("PASS " if good else "FAIL ") + name + ((" — " + detail) if detail else ""))
        print(f"\nИТОГ: {ok}/{len(results)}")

    if ok != len(results):
        print("\nЛечение: опубликовать новый релиз из master (новый тег + ассеты bootstrap/source),\n"
              "затем обновить $ReleaseTag в bootstrap.ps1 и пересобрать RELEASE_BODY.md из фактов.",
              file=sys.stderr)
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
