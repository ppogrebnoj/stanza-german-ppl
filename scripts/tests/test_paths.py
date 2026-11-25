# -*- coding: utf-8 -*-
"""Тесты контрактного каталога моделей: без сети и без установленных моделей."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import _paths  # noqa: E402


class PathsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._old = os.environ.pop("STANZA_RESOURCES_DIR", None)

    def tearDown(self) -> None:
        if self._old is not None:
            os.environ["STANZA_RESOURCES_DIR"] = self._old

    def test_default_is_contract_dir(self):
        self.assertEqual(_paths.stanza_cache_dir(), _paths.ROOT / ".stanza" / "models")
        self.assertEqual(_paths.model_dir(), _paths.ROOT / ".stanza" / "models" / "de")

    def test_env_override(self):
        os.environ["STANZA_RESOURCES_DIR"] = r"D:\stanza-models"
        self.assertEqual(_paths.stanza_cache_dir(), Path(r"D:\stanza-models"))
        self.assertEqual(_paths.model_dir(), Path(r"D:\stanza-models") / "de")


if __name__ == "__main__":
    unittest.main()
