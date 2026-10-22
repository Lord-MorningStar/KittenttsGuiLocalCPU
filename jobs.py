"""Cola de trabajos de un solo worker para no bloquear la interfaz."""
from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time
import traceback
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import config
from engine import EngineError, TTSEngine

log = config.get_logger("jobs")


@dataclass
class Job:
    id: str
    kind: str
    status: str = "queued"
    message: str = "En cola"
    progress: float = 0.0
    created: float = field(default_factory=time.time)
    started: float | None = None
    finished: float | None = None
    params: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: str | None = None
    log_path: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "message": self.message,
            "progress": round(self.progress, 3),
            "created": self.created,
            "started": self.started,
            "finished": self.finished,
            "params": self.params,
            "result": self.result,
            "error": self.error,
            "log_path": self.log_path,
        }


class JobManager:
    def __init__(self, engine: TTSEngine) -> None:
        self.engine = engine
        self.jobs: dict[str, Job] = {}
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._lock = threading.RLock()
        self._worker = threading.Thread(target=self._run, name="kitten-jobs", daemon=True)
        self._worker.start()
        self._stopped = threading.Event()

    def submit_generate(
        self, text: str, voice: str, preset: str, max_new_tokens: int
    ) -> str:
        text = (text or "").strip()
        if not text:
            raise ValueError("Escribe el texto que quieres generar.")
        if not config.assets_ready():
            raise ValueError("Faltan los assets. Ejecuta la instalación primero.")
        job = Job(
            id=uuid.uuid4().hex[:10],
            kind="generate",
            params={
                "text": text,
                "voice": voice,
                "preset": preset,
                "max_new_tokens": int(max_new_tokens),
            },
        )
        self._add(job)
        return job.id

    def submit_clone(
        self,
        reference_path: str,
        transcript: str,
        name: str,
        threads: int,
        overwrite: bool,
        consent: bool,
    ) -> str:
        if not consent:
            raise ValueError("Debes confirmar que tienes permiso para clonar esta voz.")
        if not reference_path:
            raise ValueError("Sube o graba una referencia de 6 a 30 segundos.")
        source = Path(reference_path)
        if not source.is_file():
            raise ValueError("El archivo de referencia ya no está disponible.")
        transcript = (transcript or "").strip()
        if not transcript:
            raise ValueError("Escribe el transcript exacto de la referencia.")
        name = (name or "").strip()
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,31}", name):
            raise ValueError(
                "El nombre debe empezar por letra y usar solo letras, números, _ o - (máx. 32)."
            )
        if not config.prep_ready():
            raise ValueError(
                "La clonación no está instalada. Ejecuta setup con el perfil completo."
            )
        if not config.venv_python("prep").is_file():
            raise ValueError("Falta .venv-prep. Vuelve a ejecutar la instalación.")

        uploads = config.DATA_DIR / "uploads"
        uploads.mkdir(parents=True, exist_ok=True)
        suffix = source.suffix.lower() or ".wav"
        copied = uploads / f"{uuid.uuid4().hex[:10]}{suffix}"
        shutil.copy2(source, copied)
        job = Job(
            id=uuid.uuid4().hex[:10],
            kind="clone",
            params={
                "reference": str(copied),
                "transcript": transcript,
                "name": name,
                "threads": max(1, min(4, int(threads))),
                "overwrite": bool(overwrite),
            },
        )
        self._add(job)
        return job.id

    def _add(self, job: Job) -> None:
        with self._lock:
            self.jobs[job.id] = job
            # Conserva los últimos 200 trabajos en memoria.
            if len(self.jobs) > 200:
                for key in sorted(self.jobs, key=lambda k: self.jobs[k].created)[:-200]:
                    self.jobs.pop(key, None)
        self._queue.put(job.id)
        log.info("trabajo %s en cola (%s)", job.id, job.kind)

    def get(self, job_id: str | None) -> dict[str, Any] | None:
        if not job_id:
            return None
        with self._lock:
            job = self.jobs.get(job_id)
            return job.as_dict() if job else None

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            job = self.jobs.get(job_id)
            if job is None or job.status != "queued":
                return False
            job.status = "canceled"
            job.message = "Cancelado antes de empezar"
            job.finished = time.time()
            return True

    def recent(self, limit: int = 30) -> list[dict[str, Any]]:
        path = config.OUTPUTS_DIR / "history.jsonl"
        if not path.is_file():
            return []
        lines = deque(maxlen=limit)
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if line.strip():
                        lines.append(line)
        except OSError:
            return []
        result = []
        for line in lines:
            try:
                result.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return list(reversed(result))

    def pending(self) -> int:
        with self._lock:
            return sum(1 for job in self.jobs.values() if job.status in ("queued", "running"))

    def _set(self, job: Job, **changes: Any) -> None:
        with self._lock:
            for key, value in changes.items():
                setattr(job, key, value)

    def _run(self) -> None:
        while True:
            job_id = self._queue.get()
            if job_id is None:
                self._queue.task_done()
                return
            job = self.jobs.get(job_id)
            if job is None:
                self._queue.task_done()
                continue
            if job.status == "canceled":
                self._queue.task_done()
                continue
            self._set(
                job,
                status="running",
                started=time.time(),
                message="Iniciando",
                progress=0.02,
            )
            try:
                if job.kind == "generate":
                    self._generate(job)
                elif job.kind == "clone":
                    self._clone(job)
                else:
                    raise RuntimeError(f"Tipo de trabajo desconocido: {job.kind}")
                self._set(job, status="done", finished=time.time(), progress=1.0)
                if job.result is not None:
                    job.result["finished"] = job.finished
                    self._history(job)
                log.info("trabajo %s terminado", job.id)
            except Exception as exc:
                log.exception("trabajo %s falló", job.id)
                self._set(
                    job,
                    status="error",
                    finished=time.time(),
                    error=str(exc),
                    message=f"Error: {exc}",
                )
            finally:
                self._queue.task_done()

    def _generate(self, job: Job) -> None:
        params = job.params
        self._set(job, message="Cargando motor y generando", progress=0.1)
        result = self.engine.generate(
            params["text"],
            params["voice"],
            preset=params["preset"],
            max_new_tokens=params["max_new_tokens"],
        )
        self._set(job, result=result, message="Audio generado", progress=1.0)

    def _clone(self, job: Job) -> None:
        params = job.params
        log_path = config.LOGS_DIR / f"prep-{job.id}.log"
        self._set(job, log_path=str(log_path), message="Descargando motor de la memoria")
        try:
            self.engine.unload()
        except Exception:
            log.exception("no se pudo descargar el motor antes de preparar")
        command = [
            str(config.venv_python("prep")),
            str(config.ROOT / "voice_prep.py"),
            "--reference",
            params["reference"],
            "--transcript",
            params["transcript"],
            "--name",
            params["name"],
            "--threads",
            str(params["threads"]),
        ]
        if params["overwrite"]:
            command.append("--overwrite")
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONUNBUFFERED"] = "1"
        env["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
        self._set(job, message="Preparando voz clonada", progress=0.05)
        tail: deque[str] = deque(maxlen=40)
        with log_path.open("w", encoding="utf-8") as log_handle:
            process = subprocess.Popen(
                command,
                cwd=str(config.ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=env,
            )
            assert process.stdout is not None
            for line in process.stdout:
                line = line.rstrip()
                if not line:
                    continue
                log_handle.write(line + "\n")
                log_handle.flush()
                tail.append(line)
                if line.startswith("[prep]"):
                    self._set(job, message=line[6:].strip() or "Preparando")
                    if "referencia normalizada" in line:
                        self._set(job, progress=0.15)
                    elif "cargando decodificador" in line:
                        self._set(job, progress=0.3)
                    elif "extrayendo" in line:
                        self._set(job, progress=0.55)
                    elif "voz procesada" in line:
                        self._set(job, progress=0.85)
            returncode = process.wait()
        if returncode != 0:
            detail = "\n".join(tail[-12:]) or f"código {returncode}"
            raise RuntimeError(f"voice_prep.py falló:\n{detail}")

        prep_info: dict[str, Any] = {}
        for line in tail:
            if line.startswith("[prep] OK "):
                try:
                    prep_info = json.loads(line[len("[prep] OK ") :])
                except json.JSONDecodeError:
                    pass
        self._set(job, message="Voz preparada; probando generación", progress=0.9)
        warning = None
        test: dict[str, Any] | None = None
        try:
            test = self.engine.generate(
                config.TEST_PHRASE,
                params["name"],
                preset="stable",
                max_new_tokens=500,
                output_path=config.OUTPUTS_DIR / f"clone-test-{job.id}.wav",
            )
            if test.get("warning"):
                warning = test["warning"]
        except Exception as exc:
            warning = f"La voz se preparó, pero la prueba automática falló: {exc}"
        self._set(
            job,
            result={
                "kind": "clone",
                "voice": params["name"],
                "transcript": params["transcript"],
                "reference": params["reference"],
                "prep": prep_info,
                "test": test,
                "warning": warning,
            },
            message="Voz clonada y probada" if test else "Voz clonada con advertencia",
            progress=1.0,
        )

    def _history(self, job: Job) -> None:
        if job.result is None:
            return
        record = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "job": job.id,
            "kind": job.kind,
            "result": job.result,
        }
        try:
            with (config.OUTPUTS_DIR / "history.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            log.exception("no se pudo escribir el historial")

    def shutdown(self) -> None:
        if self._stopped.is_set():
            return
        self._stopped.set()
        self._queue.put(None)
        self.engine.unload()
