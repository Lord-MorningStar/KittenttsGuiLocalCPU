#!/usr/bin/env python3
"""Prepara una voz clonada para el motor C++ de KittenTTS 2.

Se ejecuta en .venv-prep, nunca en el proceso de la interfaz. El motor debe
estar descargado antes de llamar a este script.
"""
from __future__ import annotations

import argparse
import gc
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import config  # noqa: E402


def log(message: str) -> None:
    print(f"[prep] {message}", flush=True)


def fail(message: str) -> None:
    raise RuntimeError(message)


def normalize_reference(source: Path, destination: Path) -> float:
    destination.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg_error: Exception | None = None
    try:
        import imageio_ffmpeg

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-vn",
            "-map_metadata",
            "-1",
            "-ac",
            "1",
            "-ar",
            str(config.SAMPLE_RATE if hasattr(config, "SAMPLE_RATE") else 24000),
            "-c:a",
            "pcm_s16le",
            str(destination),
        ]
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=180,
            check=False,
        )
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", "replace")[-1200:]
            raise RuntimeError(detail or f"ffmpeg terminó con código {result.returncode}")
    except Exception as exc:
        ffmpeg_error = exc

    if not destination.is_file() or destination.stat().st_size == 0:
        log(f"ffmpeg no pudo convertir ({ffmpeg_error}); probando librosa")
        import librosa
        import soundfile as sf

        waveform, _ = librosa.load(str(source), sr=24000, mono=True)
        if waveform.size == 0:
            fail("La referencia de audio está vacía.")
        sf.write(str(destination), waveform, 24000, subtype="PCM_16")

    import soundfile as sf

    try:
        info = sf.info(str(destination))
        audio, _ = sf.read(str(destination), dtype="float32", always_2d=False)
    except Exception as exc:
        raise RuntimeError(f"No se pudo leer el audio convertido: {exc}") from exc
    duration = float(info.frames / info.samplerate)
    if duration < 6.0:
        fail(
            f"La referencia dura {duration:.1f} s. Usa entre 6 y 30 segundos "
            "(idealmente 10-20 s), sin pausas largas."
        )
    if duration > 30.0:
        fail(
            f"La referencia dura {duration:.1f} s. Recórtala a 30 segundos o menos "
            "para que el transcript coincida con toda la señal."
        )
    if audio.size == 0:
        fail("La referencia no contiene muestras de audio.")
    import numpy as np

    rms = float(np.sqrt(np.mean(np.square(audio, dtype=np.float64))))
    peak = float(np.max(np.abs(audio)))
    if rms < 1e-5:
        fail("La referencia está en silencio o tiene un volumen casi nulo.")
    if peak >= 0.999:
        log("aviso: la referencia parece saturada; intenta bajar el volumen")
    log(
        f"referencia normalizada: {duration:.2f} s, {info.samplerate} Hz, "
        f"RMS={rms:.4f}, pico={peak:.3f}"
    )
    return duration


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json_atomic(path: Path, value: object) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, separators=(",", ":"))
    os.replace(temporary, path)


def prepare(args: argparse.Namespace) -> dict:
    name = args.name.strip()
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,31}", name):
        fail("El nombre debe empezar por letra y usar solo letras, números, _ o - (máx. 32).")
    transcript = args.transcript.strip()
    if not transcript:
        fail("El transcript es obligatorio: debe contener exactamente lo que se dice.")
    if len(transcript) > 4000:
        fail("El transcript es demasiado largo (máximo 4.000 caracteres).")

    config.ensure_dirs()
    if not config.assets_ready() or not config.prep_ready():
        fail(
            "Faltan assets. Ejecuta setup_assets.py en modo full antes de clonar."
        )

    reference = Path(args.reference).expanduser().resolve()
    if not reference.is_file():
        fail(f"No existe la referencia: {reference}")

    assets_config_path = config.ASSETS_DIR / "config.json"
    voices_path = config.ASSETS_DIR / "voices.json"
    model_config_path = config.MODEL_REPO_DIR / "config.json"
    if not assets_config_path.is_file() or not voices_path.is_file():
        fail("Faltan config.json o voices.json en assets/.")
    if not model_config_path.is_file():
        fail("Falta model_repo/config.json; los assets de clonación están incompletos.")

    assets_config = _read_json(assets_config_path)
    model_config = _read_json(model_config_path)
    voices = _read_json(voices_path)
    if assets_config.get("type") != "KITTEN2":
        fail("assets/config.json no es un manifiesto KITTEN2.")
    if name in voices and not args.overwrite:
        fail(f"La voz '{name}' ya existe. Usa otro nombre o marca sobrescribir.")

    decoder_name = assets_config.get("cpp_decoder", config.DEFAULT_DECODER)
    decoder_rel = (model_config.get("decoders") or {}).get(decoder_name)
    if not decoder_rel:
        fail(f"El modelo no define el decoder {decoder_name!r}.")
    decoder_path = config.MODEL_REPO_DIR / decoder_rel
    speaker_rel = model_config.get("speaker_embedding")
    lm_rel = model_config.get("lm_dir")
    if not speaker_rel or not lm_rel:
        fail("model_repo/config.json no define speaker_embedding o lm_dir.")
    speaker_path = config.MODEL_REPO_DIR / speaker_rel
    lm_dir = config.MODEL_REPO_DIR / lm_rel
    lm_config_path = lm_dir / "config.json"
    for required in (decoder_path, speaker_path, lm_config_path):
        if not required.is_file():
            fail(f"Falta el archivo necesario: {required}")

    voice_dir = config.VOICES_DIR / name
    voice_dir.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".prep-{name}-", dir=str(voice_dir)))
    try:
        reference_wav = temporary / "reference.wav"
        duration = normalize_reference(reference, reference_wav)

        log("cargando decodificador S3 y encoder de hablante")
        started = time.monotonic()
        import numpy as np
        import torch
        from safetensors import safe_open
        from kittenml.kittentts2.speaker import SpeakerEncoder
        from kittenml.kittentts2.vocoder import S3Codec

        threads = max(1, int(args.threads))
        torch.set_num_threads(threads)
        try:
            torch.set_num_interop_threads(1)
        except RuntimeError:
            pass

        codec = S3Codec(
            device="cpu",
            cache_dir=str(config.HF_CACHE_DIR),
            student_weights=str(decoder_path),
        )
        encoder = SpeakerEncoder(str(speaker_path), device="cpu")
        lm_config = _read_json(lm_config_path)
        hidden = int(lm_config.get("hidden_size", 0))
        if hidden <= 0:
            fail("lm/config.json no contiene hidden_size.")
        dtype_name = str(assets_config.get("dtype", model_config.get("dtype", "bf16")))
        dtype = torch.bfloat16 if dtype_name == "bf16" else torch.float32
        spk_dim = int(assets_config.get("speaker_embedding_dim", 512))
        state: dict[str, torch.Tensor] = {}
        for shard in sorted(lm_dir.glob("model*.safetensors")):
            with safe_open(str(shard), framework="pt", device="cpu") as handle:
                for key in handle.keys():
                    if key.startswith("spk_proj."):
                        state[key[len("spk_proj.") :]] = handle.get_tensor(key)
        if not state:
            fail("No se encontraron pesos spk_proj en el modelo; no se puede clonar.")
        projection = torch.nn.Sequential(
            torch.nn.Linear(spk_dim, hidden),
            torch.nn.LayerNorm(hidden),
        ).to(dtype).eval()
        projection.load_state_dict(state, strict=True)

        log("extrayendo embedding, tokens y condicionamiento")
        with torch.inference_mode():
            speaker = encoder(reference_wav)
            speaker_tensor = torch.from_numpy(np.asarray(speaker)).reshape(1, -1).to(dtype)
            speaker_projected = projection(speaker_tensor).float().flatten()
            conditioning = codec.reference_conditioning(reference_wav)
            reference_tokens = codec.encode_reference(reference_wav)

        entry = {
            "transcript": transcript,
            "reference_tokens": [int(x) for x in reference_tokens],
            "speaker": [float(x) for x in speaker_projected.tolist()],
            "prompt_token": conditioning["prompt_token"].long().tolist(),
            "prompt_feat": conditioning["prompt_feat"].float().tolist(),
            "embedding": conditioning["embedding"].float().tolist(),
        }
        if len(entry["speaker"]) != hidden:
            fail(
                f"Dimensión de speaker inesperada: {len(entry['speaker'])} != {hidden}"
            )
        log(
            f"voz procesada: {len(entry['reference_tokens'])} tokens de referencia, "
            f"{len(entry['speaker'])} dims de hablante"
        )

        backup = voices_path.with_name("voices.json.bak")
        shutil.copy2(voices_path, backup)
        updated = dict(voices)
        updated[name] = entry
        _write_json_atomic(voices_path, updated)
        # Verificación de lectura antes de considerar el trabajo terminado.
        _read_json(voices_path)

        final_reference = voice_dir / "reference.wav"
        os.replace(reference_wav, final_reference)
        meta = {
            "name": name,
            "transcript": transcript,
            "duration": round(duration, 3),
            "source": str(reference),
            "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "decoder": decoder_name,
            "model_revision": config.MODEL_REVISION,
        }
        _write_json_atomic(voice_dir / "meta.json", meta)
        elapsed = time.monotonic() - started
        result = {
            "name": name,
            "reference": str(final_reference),
            "duration": round(duration, 3),
            "voices": len(updated),
            "seconds": round(elapsed, 2),
        }
        log("OK " + json.dumps(result, ensure_ascii=False))
        return result
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
        gc.collect()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", required=True, help="audio de la voz (6-30 s)")
    parser.add_argument("--transcript", required=True, help="texto exacto de la referencia")
    parser.add_argument("--name", required=True, help="nombre corto de la voz")
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    try:
        prepare(args)
        return 0
    except KeyboardInterrupt:
        print("[prep] cancelado", file=sys.stderr, flush=True)
        return 130
    except Exception as exc:
        print(f"[prep] ERROR: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
