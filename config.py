"""Rutas, versiones y ajustes compartidos de KittenTTS Local."""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

APP_NAME = "KittenTTS Local"
ROOT = Path(os.environ.get("KITTEN_HOME", Path(__file__).resolve().parent)).expanduser().resolve()

ASSETS_DIR = ROOT / "assets"
MODEL_REPO_DIR = ROOT / "model_repo"
DATA_DIR = ROOT / "data"
VOICES_DIR = DATA_DIR / "voices"
OUTPUTS_DIR = ROOT / "outputs"
LOGS_DIR = ROOT / "logs"
TESTDATA_DIR = ROOT / "testdata"
CACHE_DIR = ROOT / "cache"
HF_CACHE_DIR = CACHE_DIR / "huggingface"

MODEL_REPO_ID = "KittenML/kitten-tts-2"
MODEL_REVISION = "1f00fee525c7b2e30bbe9ca9ba67529734fce9c9"
CHATTERBOX_REPO_ID = "ResembleAI/chatterbox-turbo"
CHATTERBOX_REVISION = "749d1c1a46eb10492095d68fbcf55691ccf137cd"
DEFAULT_DECODER = "student_w4"
SAMPLE_RATE = 24000

HOST = os.environ.get("KITTEN_HOST", "127.0.0.1")
PORT = int(os.environ.get("KITTEN_PORT", "7860"))
SHARE = os.environ.get("KITTEN_SHARE", "0") == "1"

TEST_PHRASE = "Hola, esta es una prueba de la voz clonada. Espero que suene natural."
TEST_REFERENCE_TEXT = (
    "Buenas tardes. Esta es una grabación de prueba para comprobar que la "
    "clonación de voz funciona correctamente. La calidad del audio es importante "
    "y debemos escuchar cada detalle."
)

RUNTIME_ASSETS = {
    "cpp/model-tq2_1.gguf": ASSETS_DIR / "model-tq2_1.gguf",
    "cpp/student_w4/decoder.pt": ASSETS_DIR / "decoder.pt",
    "cpp/student_w4/voices.json": ASSETS_DIR / "voices.json",
}

PREP_ASSETS = {
    "config.json": MODEL_REPO_DIR / "config.json",
    "lm/config.json": MODEL_REPO_DIR / "lm" / "config.json",
    "lm/model-ternary.safetensors": MODEL_REPO_DIR / "lm" / "model-ternary.safetensors",
    "speaker/model.safetensors": MODEL_REPO_DIR / "speaker" / "model.safetensors",
    "decoders/student_w4.pt": MODEL_REPO_DIR / "decoders" / "student_w4.pt",
}

HF_ASSETS = {
    CHATTERBOX_REPO_ID: {
        "s3gen_meanflow.safetensors": "s3gen_meanflow.safetensors",
    },
}


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.environ.get(name, default)))
    except (TypeError, ValueError):
        return default


def default_threads() -> int:
    return _env_int("KITTEN_THREADS", min(4, os.cpu_count() or 4), 1)


def default_decoder_threads() -> int:
    return _env_int("KITTEN_DECODER_THREADS", min(2, default_threads()), 1)


def ensure_dirs() -> None:
    for path in (
        ASSETS_DIR,
        MODEL_REPO_DIR,
        VOICES_DIR,
        OUTPUTS_DIR,
        LOGS_DIR,
        TESTDATA_DIR,
        CACHE_DIR,
        HF_CACHE_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)


def venv_python(name: str) -> Path:
    base = ROOT / f".venv-{name}"
    if sys.platform == "win32":
        return base / "Scripts" / "python.exe"
    return base / "bin" / "python"


def assets_ready() -> bool:
    return all(path.is_file() for path in RUNTIME_ASSETS.values()) and (
        ASSETS_DIR / "config.json"
    ).is_file()


def prep_ready() -> bool:
    return all(path.is_file() for path in PREP_ASSETS.values())


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    logger.propagate = False
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    logger.addHandler(stream)
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(LOGS_DIR / "app.log", encoding="utf-8")
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
    except OSError:
        pass
    return logger


def human_bytes(value: int | float) -> str:
    value = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


if __name__ == "__main__":
    ensure_dirs()
    print(f"ROOT={ROOT}")
    print(f"assets_ready={assets_ready()} prep_ready={prep_ready()}")
    print(f"threads={default_threads()} decoder_threads={default_decoder_threads()}")
