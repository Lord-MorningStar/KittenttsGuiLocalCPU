"""Motor C++ de KittenTTS 2 con carga perezosa y validación de resultados."""
from __future__ import annotations

import contextlib
import gc
import os
import re
import threading
import time
from pathlib import Path
from typing import Any

import config

log = config.get_logger("engine")


class EngineError(RuntimeError):
    pass


@contextlib.contextmanager
def _native_log():
    """Redirige el ruido de llama.cpp a logs/engine.log sin perder errores Python."""
    stream = None
    saved_out = saved_err = None
    try:
        config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
        path = config.LOGS_DIR / "engine.log"
        try:
            if path.exists() and path.stat().st_size > 10 * 1024 * 1024:
                path.unlink()
        except OSError:
            pass
        stream = open(path, "a", encoding="utf-8", buffering=1)
        saved_out = os.dup(1)
        saved_err = os.dup(2)
        os.dup2(stream.fileno(), 1)
        os.dup2(stream.fileno(), 2)
    except OSError:
        stream = None
    try:
        yield
    finally:
        if stream is not None and saved_out is not None and saved_err is not None:
            try:
                stream.flush()
                os.dup2(saved_out, 1)
                os.dup2(saved_err, 2)
            finally:
                os.close(saved_out)
                os.close(saved_err)
                stream.close()


def _slug(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-")
    return value or "voz"


class TTSEngine:
    def __init__(
        self,
        threads: int | None = None,
        decoder_threads: int | None = None,
        *,
        repack: bool = False,
    ) -> None:
        self.threads = threads or config.default_threads()
        self.decoder_threads = decoder_threads or config.default_decoder_threads()
        self.repack = repack
        self._model: Any | None = None
        self._lock = threading.RLock()
        self._last_error: str | None = None

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def _ensure_assets(self) -> None:
        if not config.assets_ready():
            raise EngineError(
                "Faltan los assets del motor. Ejecuta setup.sh o setup.bat antes de generar."
            )

    def load(self) -> Any:
        with self._lock:
            if self._model is not None:
                return self._model
            self._ensure_assets()
            log.info(
                "cargando motor: threads=%s decoder_threads=%s",
                self.threads,
                self.decoder_threads,
            )
            start = time.monotonic()
            try:
                from kitten_tts_cpp import KittenTTS
            except Exception as exc:
                raise EngineError(
                    "No se pudo importar kitten_tts_cpp. Revisa la instalación del venv."
                ) from exc
            try:
                with _native_log():
                    model = KittenTTS(
                        str(config.ASSETS_DIR),
                        model_path=str(config.ASSETS_DIR / "model-tq2_1.gguf"),
                        decoder=config.DEFAULT_DECODER,
                        threads=self.threads,
                        decoder_threads=self.decoder_threads,
                        cache_dir=str(config.CACHE_DIR / "kitten-tts"),
                        offline=True,
                        repack=self.repack,
                    )
            except Exception as exc:
                self._last_error = str(exc)
                raise EngineError(f"No se pudo cargar el motor: {exc}") from exc
            self._model = model
            self._last_error = None
            elapsed = time.monotonic() - start
            log.info(
                "motor cargado en %.1fs; %s voces; decoder=%s",
                elapsed,
                len(model.available_voices),
                model.decoder,
            )
            return model

    def unload(self) -> None:
        with self._lock:
            model, self._model = self._model, None
            if model is not None:
                try:
                    with _native_log():
                        model.close()
                except Exception:
                    log.exception("error cerrando el motor")
            gc.collect()
            log.info("motor descargado")

    def reload(self) -> Any:
        self.unload()
        return self.load()

    def voices(self) -> list[str]:
        with self._lock:
            model = self.load()
            return sorted(model.available_voices)

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "loaded": self.loaded,
                "voices": len(self._model.available_voices) if self._model else None,
                "threads": self.threads,
                "decoder_threads": self.decoder_threads,
                "decoder": getattr(self._model, "decoder", None),
                "last_error": self._last_error,
                "assets_ready": config.assets_ready(),
                "prep_ready": config.prep_ready(),
            }

    def generate(
        self,
        text: str,
        voice: str,
        *,
        preset: str = "stable",
        max_new_tokens: int = 1200,
        normalize: bool = True,
        save: bool = True,
        output_path: Path | None = None,
    ) -> dict[str, Any]:
        text = (text or "").strip()
        if not text:
            raise EngineError("El texto está vacío.")
        if len(text) > 30000:
            raise EngineError("El texto es demasiado largo (máximo 30.000 caracteres).")
        if preset not in ("stable", "expressive"):
            raise EngineError(f"Preset desconocido: {preset}")
        max_new_tokens = max(64, min(4000, int(max_new_tokens)))

        with self._lock:
            model = self.load()
            if voice not in model.available_voices:
                raise EngineError(f"Voz desconocida: {voice}")
            log.info("generando %s caracteres con voz=%s preset=%s", len(text), voice, preset)
            started = time.monotonic()
            try:
                with _native_log():
                    audio = model.generate(
                        text,
                        voice=voice,
                        preset=preset,
                        max_new_tokens=max_new_tokens,
                        normalize=normalize,
                    )
            except Exception as exc:
                self._last_error = str(exc)
                raise EngineError(f"La generación falló: {exc}") from exc
            elapsed = time.monotonic() - started
            report = model.last_report or {}

        try:
            import numpy as np

            array = np.asarray(audio, dtype="float32")
        except Exception as exc:
            raise EngineError("El motor devolvió un audio inválido.") from exc
        if array.ndim != 1 or array.size == 0:
            raise EngineError("El motor devolvió un audio vacío.")
        if not np.isfinite(array).all():
            raise EngineError("El audio contiene valores no finitos.")
        peak = float(np.max(np.abs(array)))
        if peak <= 1e-6:
            raise EngineError("El audio generado está en silencio.")
        if peak > 1.0:
            array = np.clip(array, -1.0, 1.0)

        sample_rate = int(getattr(model, "sample_rate", 24000))
        duration = float(array.size / sample_rate)
        chunks = report.get("chunks") or []
        terminated = bool(chunks) and all(bool(c.get("terminated")) for c in chunks)
        audio_tokens = sum(len(c.get("audio_tokens") or []) for c in chunks)
        warning = None
        if chunks and not terminated:
            warning = (
                "La generación alcanzó el límite de tokens sin terminar. "
                "Prueba con un texto más corto o aumenta el límite."
            )
        if duration < 0.15:
            warning = (warning + " " if warning else "") + "El audio es muy corto."

        result: dict[str, Any] = {
            "text": text,
            "voice": voice,
            "preset": preset,
            "sample_rate": sample_rate,
            "duration": duration,
            "peak": peak,
            "rtf": report.get("rtf"),
            "lm_seconds": report.get("lm_seconds"),
            "decoder_seconds": report.get("decoder_seconds"),
            "generated_tokens": report.get("generated_tokens"),
            "audio_tokens": audio_tokens,
            "terminated": terminated,
            "warning": warning,
            "elapsed": elapsed,
            "chunks": len(chunks),
        }
        if save:
            import soundfile as sf

            target = output_path or (
                config.OUTPUTS_DIR
                / f"{time.strftime('%Y%m%d-%H%M%S')}_{_slug(voice)}.wav"
            )
            target = Path(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.stem + ".tmp.wav")
            sf.write(str(temporary), array, sample_rate, subtype="PCM_16")
            os.replace(temporary, target)
            result["output_path"] = str(target)
            result["output_bytes"] = target.stat().st_size
        return result
