#!/usr/bin/env python3
"""Prueba básica del motor y, opcionalmente, el flujo completo de clonación."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from engine import TTSEngine  # noqa: E402


def _run_prep(reference: Path, transcript: str, name: str, threads: int) -> None:
    python = config.venv_python("prep")
    if not python.is_file():
        raise SystemExit(f"Falta el venv de preparación: {python}")
    command = [
        str(python),
        str(ROOT / "voice_prep.py"),
        "--reference",
        str(reference),
        "--transcript",
        transcript,
        "--name",
        name,
        "--threads",
        str(threads),
        "--overwrite",
    ]
    print("[smoke] ejecutando voice_prep.py", flush=True)
    result = subprocess.run(command, cwd=str(ROOT), check=False)
    if result.returncode != 0:
        raise SystemExit(f"voice_prep.py falló con código {result.returncode}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clone", action="store_true", help="probar clonación completa")
    parser.add_argument("--voice", default="SpanishNews")
    parser.add_argument("--name", default="PruebaES")
    parser.add_argument("--threads", type=int, default=config.default_threads())
    args = parser.parse_args()

    config.ensure_dirs()
    if not config.assets_ready():
        raise SystemExit("Faltan assets. Ejecuta setup_assets.py primero.")

    engine = TTSEngine(threads=args.threads)
    try:
        print("[smoke] generando con voz integrada", flush=True)
        baseline = engine.generate(
            "Hola, esta es una prueba del motor de voz.",
            args.voice,
            preset="stable",
            max_new_tokens=300,
            output_path=config.OUTPUTS_DIR / "smoke_builtin.wav",
        )
        print(json.dumps(baseline, ensure_ascii=False, indent=2), flush=True)
        if baseline["duration"] < 0.3:
            raise SystemExit("El audio de prueba es demasiado corto.")

        if not args.clone:
            print("[smoke] OK motor", flush=True)
            return 0

        reference = config.TESTDATA_DIR / "reference_es.wav"
        transcript_path = config.TESTDATA_DIR / "reference_es.txt"
        if not reference.is_file() or not transcript_path.is_file():
            print("[smoke] generando referencia sintética", flush=True)
            engine.unload()
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "make_test_reference.py")],
                cwd=str(ROOT),
                check=False,
            )
            if result.returncode != 0:
                raise SystemExit("No se pudo crear la referencia sintética.")
            engine = TTSEngine(threads=args.threads)
        transcript = transcript_path.read_text(encoding="utf-8").strip()

        engine.unload()
        _run_prep(reference, transcript, args.name, min(2, args.threads))
        cloned = engine.generate(
            config.TEST_PHRASE,
            args.name,
            preset="stable",
            max_new_tokens=500,
            output_path=config.OUTPUTS_DIR / f"smoke_clone_{args.name}.wav",
        )
        print(json.dumps(cloned, ensure_ascii=False, indent=2), flush=True)
        print("[smoke] OK clonación", flush=True)
        return 0
    finally:
        engine.unload()


if __name__ == "__main__":
    raise SystemExit(main())
