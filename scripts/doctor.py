#!/usr/bin/env python3
"""Diagnóstico de la instalación de KittenTTS Local."""
from __future__ import annotations

import argparse
import json
import platform
import shutil
import struct
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config  # noqa: E402

RESULTS: list[dict[str, Any]] = []


def check(name: str, ok: bool, detail: str = "", *, warning: bool = False) -> None:
    status = "ok" if ok else ("warn" if warning else "error")
    RESULTS.append({"name": name, "status": status, "detail": detail})


def check_imports(python: Path, modules: list[str], label: str) -> None:
    if not python.is_file():
        check(label, False, f"falta {python}")
        return
    import subprocess

    result = subprocess.run(
        [str(python), "-c", "import " + ", ".join(modules)],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    detail = (result.stderr or result.stdout).strip()[-1200:]
    check(label, result.returncode == 0, detail)


def check_versions(python: Path, label: str, expected: dict[str, str]) -> None:
    if not python.is_file():
        check(label, False, f"falta {python}")
        return
    code = (
        "import json,importlib.metadata as m;"
        "print(json.dumps({k:m.version(k) for k in " + repr(list(expected)) + "}))"
    )
    import subprocess

    result = subprocess.run(
        [str(python), "-c", code],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        check(label, False, result.stderr.strip()[-1200:])
        return
    try:
        versions = json.loads(result.stdout.strip().splitlines()[-1])
    except Exception:
        check(label, False, result.stdout[-500:])
        return
    problems = []
    for package, wanted in expected.items():
        got = str(versions.get(package, ""))
        if not got.startswith(wanted):
            problems.append(f"{package}={got or '?'} (esperado {wanted})")
    check(label, not problems, "; ".join(problems) if problems else json.dumps(versions))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--load", action="store_true", help="cargar el motor C++")
    parser.add_argument("--json", action="store_true", help="salida JSON")
    args = parser.parse_args()

    config.ensure_dirs()
    check("python", sys.version_info >= (3, 10), sys.version.split()[0])
    check("64 bits", struct.calcsize("P") * 8 == 64, str(struct.calcsize("P") * 8))
    check("plataforma", True, platform.platform())

    cpp_python = config.venv_python("cpp")
    prep_python = config.venv_python("prep")
    check("venv-cpp", cpp_python.is_file(), str(cpp_python))
    check("venv-prep", prep_python.is_file(), str(prep_python), warning=not config.prep_ready())
    check_imports(cpp_python, ["torch", "kitten_tts_cpp", "gradio", "soundfile", "psutil"], "imports C++")
    check_versions(
        cpp_python,
        "versiones C++",
        {"torch": "2.13.0", "kitten-tts-cpp": "0.2.0", "gradio": "6.30.0"},
    )
    if config.prep_ready():
        check_imports(
            prep_python,
            ["torch", "torchaudio", "kittenml", "imageio_ffmpeg", "safetensors"],
            "imports preparación",
        )
        check_versions(
            prep_python,
            "versiones preparación",
            {"torch": "2.11.0", "torchaudio": "2.11.0", "kittenml": "0.9.6"},
        )

    check("assets generación", config.assets_ready(), str(config.ASSETS_DIR))
    check("assets clonación", config.prep_ready(), str(config.MODEL_REPO_DIR))
    for path, expected_size in (
        (config.ASSETS_DIR / "model-tq2_1.gguf", 1029076832),
        (config.ASSETS_DIR / "decoder.pt", 312339253),
    ):
        if path.is_file():
            size = path.stat().st_size
            check(
                path.name,
                size == expected_size,
                f"{size} bytes (esperado {expected_size})",
            )
        else:
            check(path.name, False, "falta")
    voices_path = config.ASSETS_DIR / "voices.json"
    if voices_path.is_file():
        try:
            count = len(json.loads(voices_path.read_text(encoding="utf-8")))
            check("voices.json", count > 0, f"{count} voces")
        except Exception as exc:
            check("voices.json", False, str(exc))
    else:
        check("voices.json", False, "falta")

    s3gen = list(
        config.HF_CACHE_DIR.glob(
            "models--ResembleAI--chatterbox-turbo/snapshots/*/s3gen_meanflow.safetensors"
        )
    )
    check(
        "s3gen",
        bool(s3gen),
        str(s3gen[0]) if s3gen else "falta en la caché de Hugging Face",
        warning=True,
    )

    try:
        import psutil

        mem = psutil.virtual_memory()
        check(
            "RAM",
            mem.available >= 3 * 1024**3,
            f"{config.human_bytes(mem.available)} disponibles de {config.human_bytes(mem.total)}",
            warning=mem.available < 6 * 1024**3,
        )
    except Exception:
        pass
    try:
        usage = shutil.disk_usage(config.ROOT)
        check(
            "disco",
            usage.free >= 2 * 1024**3,
            f"{config.human_bytes(usage.free)} libres",
            warning=usage.free < 5 * 1024**3,
        )
    except OSError:
        pass
    check("hilos", config.default_threads() >= 1, str(config.default_threads()))

    if args.load:
        if not config.assets_ready():
            check("carga del motor", False, "faltan assets")
        else:
            try:
                from engine import TTSEngine

                engine = TTSEngine()
                voices = engine.voices()
                check("carga del motor", True, f"{len(voices)} voces")
                engine.unload()
            except Exception as exc:
                check("carga del motor", False, str(exc))

    errors = [item for item in RESULTS if item["status"] == "error"]
    warnings = [item for item in RESULTS if item["status"] == "warn"]
    if args.json:
        print(json.dumps({"results": RESULTS, "errors": len(errors), "warnings": len(warnings)}, ensure_ascii=False, indent=2))
    else:
        symbols = {"ok": "OK  ", "warn": "AVISO", "error": "ERROR"}
        for item in RESULTS:
            print(f"{symbols[item['status']]:5} {item['name']}: {item['detail']}")
        print(f"\n{len(errors)} errores, {len(warnings)} avisos")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
