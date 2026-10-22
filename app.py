#!/usr/bin/env python3
"""Interfaz local de KittenTTS 2: generación y clonación de voz en CPU."""
from __future__ import annotations

import argparse
import atexit
import json
import platform
import shutil
import sys
from pathlib import Path
from typing import Any

import config
from engine import TTSEngine
from jobs import JobManager

config.ensure_dirs()

import gradio as gr  # noqa: E402

ENGINE = TTSEngine()
MANAGER = JobManager(ENGINE)
atexit.register(MANAGER.shutdown)


def _read_voices() -> dict[str, Any]:
    path = config.ASSETS_DIR / "voices.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _voice_choices() -> list[str]:
    return sorted(_read_voices())


def _default_voice(choices: list[str]) -> str:
    for name in ("SpanishNews", "Spanish", "Bruno"):
        if name in choices:
            return name
    return choices[0] if choices else ""


def _fmt_bytes(value: float) -> str:
    return config.human_bytes(value)


def _status_markdown(job: dict[str, Any] | None) -> str:
    if not job:
        return "Sin trabajo activo."
    status = job["status"]
    message = job.get("message") or ""
    if status == "queued":
        return f"**En cola.** {message}"
    if status == "running":
        return f"**Trabajando.** {message}  \nProgreso: {job.get('progress', 0) * 100:.0f}%"
    if status == "canceled":
        return f"**Cancelado.** {message}"
    if status == "error":
        error = (job.get("error") or "").strip()
        return f"**Error.**\n\n```\n{error[:4000]}\n```"
    result = job.get("result") or {}
    if job["kind"] == "generate":
        warning = result.get("warning")
        lines = [
            "**Audio listo.**",
            f"- Voz: `{result.get('voice')}`",
            f"- Duración: {result.get('duration', 0):.2f} s",
            f"- RTF: {result.get('rtf') or 0:.2f}",
            f"- Tokens: {result.get('generated_tokens')}",
            f"- Terminó: {'sí' if result.get('terminated') else 'no'}",
            f"- Archivo: `{result.get('output_path')}`",
        ]
        if warning:
            lines.append(f"- **Aviso:** {warning}")
        return "\n".join(lines)
    warning = result.get("warning")
    lines = [
        "**Voz clonada.**",
        f"- Nombre: `{result.get('voice')}`",
    ]
    prep = result.get("prep") or {}
    if prep:
        lines.append(f"- Referencia: {prep.get('duration', 0):.2f} s")
        lines.append(f"- Voces totales: {prep.get('voices')}")
    test = result.get("test") or {}
    if test:
        lines.append(f"- Prueba: {test.get('duration', 0):.2f} s, RTF {test.get('rtf') or 0:.2f}")
    if warning:
        lines.append(f"- **Aviso:** {warning}")
    return "\n".join(lines)


def _voice_rows() -> tuple[list[list[Any]], str]:
    voices = _read_voices()
    custom: set[str] = set()
    if config.VOICES_DIR.is_dir():
        for path in config.VOICES_DIR.iterdir():
            if path.is_dir() and (path / "meta.json").is_file():
                custom.add(path.name)
    rows: list[list[Any]] = []
    for name in sorted(voices, key=lambda n: (n not in custom, n.lower())):
        entry = voices[name]
        transcript = str(entry.get("transcript", "")).replace("\n", " ")
        if len(transcript) > 160:
            transcript = transcript[:157] + "..."
        rows.append([name, "Clonada" if name in custom else "Integrada", transcript])
    summary = f"**{len(rows)} voces disponibles**, {len(custom)} clonadas."
    return rows, summary


def _history_rows() -> list[list[Any]]:
    rows: list[list[Any]] = []
    for record in MANAGER.recent(30):
        result = record.get("result") or {}
        kind = record.get("kind", "")
        if kind == "generate":
            voice = result.get("voice")
            duration = result.get("duration")
            rtf = result.get("rtf")
            path = result.get("output_path")
            preview = result.get("text", "")
            warning = result.get("warning") or ""
        else:
            test = result.get("test") or {}
            voice = result.get("voice")
            duration = test.get("duration")
            rtf = test.get("rtf")
            path = test.get("output_path")
            preview = result.get("transcript", "")
            warning = result.get("warning") or ""
        rows.append(
            [
                record.get("time", ""),
                "Clonar" if kind == "clone" else "Generar",
                voice or "",
                f"{duration:.2f}" if isinstance(duration, (int, float)) else "",
                f"{rtf:.2f}" if isinstance(rtf, (int, float)) else "",
                path or "",
                warning,
                (preview[:100] + "...") if len(preview) > 100 else preview,
            ]
        )
    return rows


def _diagnostics() -> str:
    status = ENGINE.status()
    lines = [
        f"## {config.APP_NAME}",
        f"- Plataforma: `{platform.platform()}`",
        f"- Python: `{sys.version.split()[0]}`",
        f"- Raíz: `{config.ROOT}`",
        f"- Assets de generación: {'sí' if config.assets_ready() else 'no'}",
        f"- Assets de clonación: {'sí' if config.prep_ready() else 'no'}",
        f"- Motor cargado: {'sí' if status['loaded'] else 'no'}",
        f"- Hilos: {status['threads']} (decoder {status['decoder_threads']})",
        f"- Voces: {status['voices'] if status['voices'] is not None else 'se cargan al generar'}",
        f"- Puerto: {config.PORT}",
    ]
    try:
        import psutil

        mem = psutil.virtual_memory()
        lines.append(
            f"- RAM: {_fmt_bytes(mem.available)} disponibles de {_fmt_bytes(mem.total)}"
        )
    except Exception:
        pass
    try:
        usage = shutil.disk_usage(config.ROOT)
        lines.append(f"- Disco: {_fmt_bytes(usage.free)} libres de {_fmt_bytes(usage.total)}")
    except OSError:
        pass
    try:
        for package in ("torch", "kitten-tts-cpp", "gradio", "soundfile"):
            from importlib.metadata import version

            lines.append(f"- {package}: `{version(package)}`")
    except Exception:
        pass
    for relative in ("assets/model-tq2_1.gguf", "assets/decoder.pt", "assets/voices.json"):
        path = config.ROOT / relative
        if path.is_file():
            lines.append(f"- `{relative}`: {_fmt_bytes(path.stat().st_size)}")
    log = config.LOGS_DIR / "app.log"
    if log.is_file():
        lines.append(f"- Log: `{log}`")
    return "\n".join(lines)


def submit_generate(text: str, voice: str, preset: str, max_tokens: float):
    try:
        job_id = MANAGER.submit_generate(text, voice, preset, int(max_tokens))
    except Exception as exc:
        return "", f"**Error.** {exc}", None, None, None
    return job_id, "**En cola.** El motor se cargará si hace falta.", None, None, None


def poll_generate(job_id: str | None):
    job = MANAGER.get(job_id)
    if not job:
        return "Sin trabajo activo.", None, None, None
    status = _status_markdown(job)
    if job["status"] == "done":
        result = job.get("result") or {}
        return status, result.get("output_path"), result, result.get("output_path")
    if job["status"] == "error":
        return status, None, {"error": job.get("error")}, job.get("log_path")
    return status, None, None, None


def submit_clone(
    reference: str | None,
    transcript: str,
    name: str,
    threads: float,
    overwrite: bool,
    consent: bool,
):
    try:
        job_id = MANAGER.submit_clone(
            reference or "",
            transcript,
            name,
            int(threads),
            bool(overwrite),
            bool(consent),
        )
    except Exception as exc:
        return "", f"**Error.** {exc}", None, None, None, gr.update(), gr.update()
    return (
        job_id,
        "**En cola.** La preparación puede tardar varios minutos.",
        None,
        None,
        None,
        gr.update(),
        gr.update(),
    )


def poll_clone(job_id: str | None):
    job = MANAGER.get(job_id)
    if not job:
        return "Sin trabajo activo.", None, None, None, gr.update(), gr.update()
    status = _status_markdown(job)
    if job["status"] == "done":
        result = job.get("result") or {}
        test = result.get("test") or {}
        choices = _voice_choices()
        return (
            status,
            test.get("output_path"),
            result,
            job.get("log_path"),
            gr.update(choices=choices, value=result.get("voice")),
            _voice_rows()[1],
        )
    if job["status"] == "error":
        return status, None, {"error": job.get("error")}, job.get("log_path"), gr.update(), gr.update()
    return status, None, None, job.get("log_path"), gr.update(), gr.update()


def refresh_voices():
    rows, summary = _voice_rows()
    return rows, summary, gr.update(choices=_voice_choices())


def refresh_history():
    return _history_rows()


def build_app() -> gr.Blocks:
    voices = _voice_choices()
    default_voice = _default_voice(voices)
    voice_rows, voice_summary = _voice_rows()

    with gr.Blocks(
        title=config.APP_NAME,
        analytics_enabled=False,
        fill_width=True,
    ) as demo:
        gr.Markdown(
            f"""
# {config.APP_NAME}

Generación y clonación de voz **local**, en CPU y sin GPU. Todo se queda en tu equipo.
La primera generación tarda más porque carga el modelo en memoria; después se reutiliza.

> La clonación solo debe usarse con voces propias o con permiso explícito. No redistribuyas los pesos del modelo.
"""
        )

        gen_job = gr.State("")
        clone_job = gr.State("")

        with gr.Tabs():
            with gr.Tab("Generar"):
                with gr.Row():
                    with gr.Column(scale=3):
                        text = gr.Textbox(
                            label="Texto",
                            lines=7,
                            max_lines=20,
                            placeholder="Escribe aquí el texto que quieres convertir en voz...",
                            value="Hola, esta es una prueba de KittenTTS Local.",
                        )
                        with gr.Row():
                            gen_voice = gr.Dropdown(
                                choices=voices,
                                value=default_voice,
                                label="Voz",
                                filterable=True,
                            )
                            preset = gr.Radio(
                                choices=["stable", "expressive"],
                                value="stable",
                                label="Preset",
                            )
                        max_tokens = gr.Slider(
                            minimum=200,
                            maximum=2000,
                            value=1200,
                            step=100,
                            label="Máximo de tokens por chunk",
                            info="Más tokens permiten textos largos; valores altos tardan más.",
                        )
                        gen_button = gr.Button("Generar audio", variant="primary")
                    with gr.Column(scale=2):
                        gen_status = gr.Markdown("Sin trabajo activo.")
                        gen_audio = gr.Audio(
                            label="Resultado",
                            type="filepath",
                            interactive=False,
                            autoplay=False,
                        )
                        gen_download = gr.File(label="Descargar WAV", interactive=False)
                        gen_report = gr.JSON(label="Detalle técnico", open=False)
                gen_timer = gr.Timer(1.0)
                gen_button.click(
                    submit_generate,
                    inputs=[text, gen_voice, preset, max_tokens],
                    outputs=[gen_job, gen_status, gen_audio, gen_report, gen_download],
                    queue=False,
                )
                gen_timer.tick(
                    poll_generate,
                    inputs=[gen_job],
                    outputs=[gen_status, gen_audio, gen_report, gen_download],
                    queue=False,
                )

            with gr.Tab("Clonar voz"):
                gr.Markdown(
                    """
Sube o graba **6–30 segundos** de una sola persona, sin música ni ruido.
Escribe el **transcript exacto** de lo que se dice. La prueba automática se ejecuta al terminar.
"""
                )
                with gr.Row():
                    with gr.Column(scale=3):
                        clone_ref = gr.Audio(
                            label="Referencia de voz",
                            sources=["upload", "microphone"],
                            type="filepath",
                        )
                        clone_transcript = gr.Textbox(
                            label="Transcript exacto",
                            lines=3,
                            placeholder="Lo que se dice en la grabación, palabra por palabra.",
                        )
                        with gr.Row():
                            clone_name = gr.Textbox(
                                label="Nombre de la voz",
                                placeholder="MiVoz",
                                max_length=32,
                            )
                            clone_threads = gr.Slider(
                                minimum=1,
                                maximum=4,
                                value=2,
                                step=1,
                                label="Hilos de preparación",
                                info="2 es un buen equilibrio en PCs de 8–12 GB.",
                            )
                        with gr.Row():
                            clone_overwrite = gr.Checkbox(
                                label="Sobrescribir si existe",
                                value=False,
                            )
                            clone_consent = gr.Checkbox(
                                label="Tengo permiso para clonar esta voz",
                                value=False,
                            )
                        clone_button = gr.Button("Clonar y probar", variant="primary")
                    with gr.Column(scale=2):
                        clone_status = gr.Markdown("Sin trabajo activo.")
                        clone_audio = gr.Audio(
                            label="Prueba automática",
                            type="filepath",
                            interactive=False,
                            autoplay=False,
                        )
                        clone_report = gr.JSON(label="Detalle técnico", open=False)
                        clone_log = gr.File(label="Log de preparación", interactive=False)
                        clone_voices_summary = gr.Markdown(voice_summary)
                clone_timer = gr.Timer(1.0)
                clone_button.click(
                    submit_clone,
                    inputs=[
                        clone_ref,
                        clone_transcript,
                        clone_name,
                        clone_threads,
                        clone_overwrite,
                        clone_consent,
                    ],
                    outputs=[
                        clone_job,
                        clone_status,
                        clone_audio,
                        clone_report,
                        clone_log,
                        gen_voice,
                        clone_voices_summary,
                    ],
                    queue=False,
                )
                clone_timer.tick(
                    poll_clone,
                    inputs=[clone_job],
                    outputs=[
                        clone_status,
                        clone_audio,
                        clone_report,
                        clone_log,
                        gen_voice,
                        clone_voices_summary,
                    ],
                    queue=False,
                )

            with gr.Tab("Voces"):
                voices_summary = gr.Markdown(voice_summary)
                voices_table = gr.Dataframe(
                    value=voice_rows,
                    headers=["Voz", "Tipo", "Transcript"],
                    datatype=["str", "str", "str"],
                    interactive=False,
                    wrap=True,
                    max_height=520,
                    show_search="search",
                )
                refresh_voices_button = gr.Button("Actualizar lista")
                refresh_voices_button.click(
                    refresh_voices,
                    outputs=[voices_table, voices_summary, gen_voice],
                    queue=False,
                )

            with gr.Tab("Historial"):
                history_table = gr.Dataframe(
                    value=_history_rows(),
                    headers=["Fecha", "Tipo", "Voz", "Duración", "RTF", "Archivo", "Aviso", "Texto"],
                    datatype=["str", "str", "str", "str", "str", "str", "str", "str"],
                    interactive=False,
                    wrap=True,
                    max_height=520,
                    show_search="search",
                )
                refresh_history_button = gr.Button("Actualizar historial")
                refresh_history_button.click(
                    refresh_history, outputs=[history_table], queue=False
                )

            with gr.Tab("Diagnóstico"):
                diagnostics = gr.Markdown(_diagnostics())
                diag_button = gr.Button("Actualizar diagnóstico")
                diag_timer = gr.Timer(5.0)
                diag_button.click(_diagnostics, outputs=[diagnostics], queue=False)
                diag_timer.tick(_diagnostics, outputs=[diagnostics], queue=False)

        gr.Markdown(
            """
---
Consejo: en PCs de 8 GB cierra otras aplicaciones y usa la voz `student_w4` con 2–4 hilos.
Los logs están en `logs/`. La licencia de los pesos es de Stellon Labs; revisa el repositorio del modelo.
"""
        )

    return demo


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=config.HOST)
    parser.add_argument("--port", type=int, default=config.PORT)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--share", action="store_true")
    args = parser.parse_args()
    config.HOST = args.host
    config.PORT = args.port
    config.SHARE = args.share or config.SHARE

    if not config.assets_ready():
        print(
            "Faltan assets. Ejecuta setup.sh (Linux) o setup.bat (Windows) antes de abrir la app.",
            file=sys.stderr,
        )
    demo = build_app()
    demo.queue(default_concurrency_limit=4)
    demo.launch(
        server_name=args.host,
        server_port=args.port,
        share=config.SHARE,
        inbrowser=not args.no_browser,
        show_error=True,
        allowed_paths=[
            str(config.OUTPUTS_DIR),
            str(config.TESTDATA_DIR),
            str(config.DATA_DIR),
            str(config.LOGS_DIR),
        ],
        max_file_size="200mb",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
