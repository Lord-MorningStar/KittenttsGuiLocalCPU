#!/usr/bin/env python3
"""Genera una referencia sintética de prueba con una voz integrada."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from engine import TTSEngine  # noqa: E402


def main() -> int:
    config.ensure_dirs()
    engine = TTSEngine()
    try:
        result = engine.generate(
            config.TEST_REFERENCE_TEXT,
            "SpanishNews",
            preset="stable",
            max_new_tokens=800,
            output_path=config.TESTDATA_DIR / "reference_es.wav",
        )
        (config.TESTDATA_DIR / "reference_es.txt").write_text(
            config.TEST_REFERENCE_TEXT + "\n", encoding="utf-8"
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result["duration"] < 6.0:
            print(
                "ERROR: la referencia sintética dura menos de 6 s; alarga el texto.",
                file=sys.stderr,
            )
            return 1
        return 0
    finally:
        engine.unload()


if __name__ == "__main__":
    raise SystemExit(main())
