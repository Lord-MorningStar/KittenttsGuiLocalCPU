#!/usr/bin/env python3
"""Descarga y ensambla los assets locales de KittenTTS 2.

Uso:
    .venv-prep/bin/python setup_assets.py
    .venv-prep/bin/python setup_assets.py --profile runtime
    .venv-prep/bin/python setup_assets.py --check
    .venv-prep/bin/python setup_assets.py --force
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import config


def log(message: str) -> None:
    print(f"[assets] {message}", flush=True)


def _download(repo_id: str, filename: str, revision: str, destination: Path) -> Path:
    try:
        from huggingface_hub import hf_hub_download
    except Exception as exc:
        raise RuntimeError(
            "Falta huggingface_hub. Ejecuta primero setup.sh o scripts\\setup.ps1."
        ) from exc

    destination.parent.mkdir(parents=True, exist_ok=True)
    token = os.environ.get("HF_TOKEN") or None
    path = hf_hub_download(
        repo_id=repo_id,
        filename=filename,
        revision=revision,
        local_dir=str(destination.parent),
        token=token,
    )
    result = Path(path)
    if result.resolve() != destination.resolve():
        link_or_copy(result, destination)
        try:
            result.unlink()
        except OSError:
            pass
    if not destination.is_file() or destination.stat().st_size == 0:
        raise RuntimeError(f"Descarga vacía: {repo_id}/{filename}")
    return destination


def link_or_copy(source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    if temporary.exists():
        temporary.unlink()
    try:
        os.link(source, temporary)
    except OSError:
        shutil.copy2(source, temporary)
    os.replace(temporary, destination)
    return destination


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: object, *, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if compact:
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    else:
        text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def _merge_voices(builtin_path: Path, target_path: Path) -> None:
    builtin = _read_json(builtin_path)
    existing = _read_json(target_path) if target_path.is_file() else {}
    merged = dict(builtin)
    preserved = 0
    for name, entry in existing.items():
        if name not in merged:
            merged[name] = entry
            preserved += 1
    if target_path.is_file():
        backup = target_path.with_name("voices.json.bak")
        shutil.copy2(target_path, backup)
    _write_json(target_path, merged, compact=True)
    log(
        f"voces: {len(builtin)} integradas, {preserved} personalizadas conservadas "
        f"({len(merged)} total)"
    )


def _make_assets_config(model_config: dict) -> dict:
    public = {key: value for key, value in model_config.items() if key != "cpp"}
    public["cpp_decoder"] = config.DEFAULT_DECODER
    public.pop("default_decoder", None)
    return public


def _expected_sizes(model_config: dict) -> dict[str, int]:
    sizes: dict[str, int] = {}
    cpp = model_config.get("cpp", {})
    gguf = cpp.get("gguf", {})
    if gguf.get("file") and gguf.get("size"):
        sizes[gguf["file"]] = int(gguf["size"])
    decoder = cpp.get("decoders", {}).get(config.DEFAULT_DECODER, {})
    for key in ("torchscript", "voices"):
        item = decoder.get(key, {})
        if item.get("file") and item.get("size"):
            sizes[item["file"]] = int(item["size"])
    return sizes


def check(profile: str = "full") -> list[str]:
    problems: list[str] = []
    required = [config.ASSETS_DIR / "config.json"]
    required += list(config.RUNTIME_ASSETS.values())
    if profile == "full":
        required += list(config.PREP_ASSETS.values())
    for path in required:
        if not path.is_file() or path.stat().st_size == 0:
            problems.append(f"falta o está vacío: {path}")
    if not (config.ASSETS_DIR / "voices.json").is_file():
        problems.append(f"falta: {config.ASSETS_DIR / 'voices.json'}")
    if profile == "full":
        snapshots = config.HF_CACHE_DIR.glob(
            "models--ResembleAI--chatterbox-turbo/snapshots/*/s3gen_meanflow.safetensors"
        )
        if not any(path.is_file() for path in snapshots):
            problems.append("falta s3gen_meanflow.safetensors en la caché de Hugging Face")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        choices=("full", "runtime"),
        default="full",
        help="full instala clonación; runtime solo generación",
    )
    parser.add_argument("--check", action="store_true", help="solo validar")
    parser.add_argument("--force", action="store_true", help="volver a descargar")
    parser.add_argument("--keep-downloads", action="store_true", help="no borrar temporales")
    args = parser.parse_args()

    config.ensure_dirs()
    if args.check:
        problems = check(args.profile)
        if problems:
            for problem in problems:
                print(f"[assets] ERROR {problem}")
            return 1
        log("assets completos")
        return 0

    downloads = Path(tempfile.mkdtemp(prefix="kitten-downloads-", dir=str(config.CACHE_DIR)))
    try:
        log(f"descargando configuración de {config.MODEL_REPO_ID}")
        model_config_path = _download(
            config.MODEL_REPO_ID,
            "config.json",
            config.MODEL_REVISION,
            downloads / "config.json",
        )
        model_config = _read_json(model_config_path)
        if model_config.get("type") != "KITTEN2":
            raise RuntimeError("El modelo descargado no es KITTEN2")

        expected = _expected_sizes(model_config)
        runtime_files = {
            "cpp/model-tq2_1.gguf": config.ASSETS_DIR / "model-tq2_1.gguf",
            "cpp/student_w4/decoder.pt": config.ASSETS_DIR / "decoder.pt",
            "cpp/student_w4/voices.json": downloads / "builtin-voices.json",
        }
        for remote, destination in runtime_files.items():
            if destination.is_file() and not args.force:
                if destination.name != "builtin-voices.json":
                    if destination.stat().st_size == expected.get(remote, destination.stat().st_size):
                        log(f"ya existe: {destination.relative_to(config.ROOT)}")
                        continue
            if destination.is_file() and args.force:
                destination.unlink()
            log(f"descargando {remote}")
            _download(config.MODEL_REPO_ID, remote, config.MODEL_REVISION, destination)
            if remote in expected and destination.stat().st_size != expected[remote]:
                raise RuntimeError(
                    f"tamaño incorrecto para {remote}: {destination.stat().st_size} != {expected[remote]}"
                )

        if not args.force and (config.ASSETS_DIR / "config.json").is_file():
            log("config.json de assets ya existe")
        _write_json(config.ASSETS_DIR / "config.json", _make_assets_config(model_config))
        _merge_voices(downloads / "builtin-voices.json", config.ASSETS_DIR / "voices.json")
        log("assets de generación listos")

        if args.profile == "full":
            for remote, destination in config.PREP_ASSETS.items():
                if destination.is_file() and not args.force and destination.stat().st_size > 0:
                    log(f"ya existe: {destination.relative_to(config.ROOT)}")
                    continue
                log(f"descargando {remote}")
                _download(config.MODEL_REPO_ID, remote, config.MODEL_REVISION, destination)

            log("descargando decoder de voz (chatterbox-turbo)")
            try:
                from huggingface_hub import hf_hub_download
            except Exception as exc:
                raise RuntimeError("Falta huggingface_hub en el venv de preparación") from exc
            s3gen = Path(
                hf_hub_download(
                    repo_id=config.CHATTERBOX_REPO_ID,
                    filename="s3gen_meanflow.safetensors",
                    revision=config.CHATTERBOX_REVISION,
                    cache_dir=str(config.HF_CACHE_DIR),
                    token=os.environ.get("HF_TOKEN") or None,
                )
            )
            log(f"s3gen listo: {s3gen} ({config.human_bytes(s3gen.stat().st_size)})")

        problems = check(args.profile)
        if problems:
            raise RuntimeError("; ".join(problems))
        log("instalación de assets completa")
        return 0
    finally:
        if not args.keep_downloads:
            shutil.rmtree(downloads, ignore_errors=True)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n[assets] cancelado", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"[assets] ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
