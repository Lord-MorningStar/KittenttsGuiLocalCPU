# KittenTTS Local

Aplicación local para **generar voz** y **clonar voces** con KittenTTS 2 en CPU.
Incluye interfaz en español, cola de trabajos, historial y scripts de instalación
para Windows y Linux. Todo el audio se procesa en tu equipo.

> Probado en Linux/WSL. Los scripts de Windows están incluidos, pero todavía deben
> validarse en la laptop Windows de destino.

## Requisitos

- Windows 10/11 x64 o Linux x64.
- CPU con AVX2. GPU no necesaria.
- **8 GB de RAM mínimo**; 12 GB recomendados.
- **8 GB libres** mínimo; 10 GB recomendados (assets ~3.3 GB + entornos ~3.3 GB).
- Internet solo durante la instalación.

El instalador busca Python 3.10–3.14 de 64 bits. En Windows, si no lo encuentra,
ofrece instalar Python 3.12 x64 para el usuario actual.

## Instalación en Windows

1. Descomprime la carpeta completa, por ejemplo en:
   `%LOCALAPPDATA%\KittenTTS`
2. Haz doble clic en **`setup.bat`**.
3. Espera la descarga de dependencias y assets. Puede tardar bastante.
4. Al terminar, abre **`KittenTTS Local`** en el escritorio o ejecuta **`run.bat`**.

Opciones:

```bat
setup.bat --runtime-only
setup.bat --skip-assets
setup.bat --force
```

- `--runtime-only`: solo generación; no instala el entorno de clonación.
- `--skip-assets`: no descarga assets (útil si ya existen).
- `--force`: recrea los entornos virtuales.

## Instalación en Linux

```bash
./setup.sh
./run.sh
```

Opciones equivalentes:

```bash
./setup.sh --runtime-only
./setup.sh --skip-assets
./setup.sh --force
```

La app abre en `http://127.0.0.1:7860`.

## Uso

### Generar audio

1. Abre la pestaña **Generar audio**.
2. Escribe el texto y elige una voz integrada o clonada.
3. Ajusta los hilos si hace falta.
4. Pulsa **Generar**. El trabajo sigue en segundo plano; la página consulta el estado.
5. Descarga el WAV desde el reproductor.

### Clonar una voz

1. Prepara un audio de **6–30 segundos** (ideal 10–20 s):
   - una sola persona;
   - sin música, ruido ni otras voces;
   - volumen normal, sin saturación.
2. Escribe el **transcript exacto** de lo que se dice.
3. Elige un nombre: letras, números, `_` o `-`; máximo 32 caracteres.
4. Marca el consentimiento y pulsa **Clonar voz**.
5. La app prepara la voz y hace una prueba automática. Si la prueba falla, la voz
   se conserva con una advertencia para que puedas revisarla.

No se permite clonar voces sin permiso. Usa solo audios propios o con autorización.

### Consejos de calidad

- Referencias limpias y con voz natural funcionan mejor que audios con ruido.
- El transcript debe coincidir palabra por palabra con la referencia.
- Para español, escribe texto con acentos y puntuación normal.
- Si el audio sale cortado, aumenta el límite de tokens o acorta el texto.
- En PCs lentos, usa 2–4 hilos y evita otras aplicaciones pesadas.

## Rendimiento observado

En el equipo de desarrollo (7.5 GB RAM, 4 hilos):

- Carga del motor: ~4–10 s.
- Generación de 3 s de audio: ~40 s.
- Generación de 6 s de audio: ~70 s.
- Preparación de una voz: ~55 s y ~2.7 GB de pico de RAM.

En un i5-7200U la generación será más lenta. Es normal: el objetivo es correctitud,
no velocidad.

## Diagnóstico

```bash
# Linux
.venv-cpp/bin/python scripts/doctor.py --load
.venv-cpp/bin/python setup_assets.py --check

# Windows
.venv-cpp\Scripts\python.exe scripts\doctor.py --load
.venv-cpp\Scripts\python.exe setup_assets.py --check
```

Pruebas rápidas:

```bash
.venv-cpp/bin/python scripts/smoke_test.py
.venv-cpp/bin/python scripts/smoke_test.py --clone
```

## Configuración

Variables de entorno opcionales:

| Variable | Efecto | Defecto |
|---|---|---|
| `KITTEN_HOME` | carpeta raíz del proyecto | carpeta de `config.py` |
| `KITTEN_HOST` | interfaz de escucha | `127.0.0.1` |
| `KITTEN_PORT` | puerto de la app | `7860` |
| `KITTEN_SHARE` | `1` para enlace público de Gradio | `0` |
| `KITTEN_THREADS` | hilos de generación | hasta 4 |
| `KITTEN_DECODER_THREADS` | hilos del decodificador | hasta 2 |

También puedes pasar argumentos a la app:

```bash
./run.sh --port 7861 --no-browser
```

```bat
run.bat --port 7861 --no-browser
```

## Estructura

```
app.py               interfaz Gradio
config.py            rutas, versiones y ajustes
engine.py            motor C++ de generación
voice_prep.py        preparación de voces clonadas
jobs.py              cola de trabajos e historial
setup_assets.py      descarga y ensamblado de assets
setup.bat/.sh        instalación
run.bat/.sh          arranque
scripts/             diagnóstico y pruebas
assets/              modelo de generación (descargado)
model_repo/          piezas para preparar voces (descargado)
cache/               caché de Hugging Face
data/voices/         referencias y metadatos de voces clonadas
outputs/             audios generados e historial
logs/                logs de la app, el motor y la instalación
```

## Logs y problemas frecuentes

- `logs/setup.log`: instalación.
- `logs/app.log`: interfaz y trabajos.
- `logs/engine.log`: salida nativa del motor C++.
- `logs/prep-*.log`: preparación de voces.

Si falla la instalación:

1. Revisa `logs/setup.log`.
2. Ejecuta `setup.bat` de nuevo; es idempotente.
3. Comprueba que hay Internet y ~8 GB libres.
4. Si el antivirus bloquea la instalación, permite la carpeta del proyecto.
5. En Windows, evita OneDrive, rutas de red y discos exFAT.
6. Si falla la carga de `kitten_tts_cpp`, instala Microsoft Visual C++
   Redistributable 2015–2022 x64.

Si la app no arranca, ejecuta `scripts\doctor.py` y revisa que existan
`.venv-cpp\Scripts\python.exe` y `assets\model-tq2_1.gguf`.

## Licencias y privacidad

- El código de este proyecto se distribuye bajo Apache-2.0.
- Los pesos de KittenTTS 2 están bajo la **Stellon Labs Community License**.
  No se incluyen en este repositorio; `setup_assets.py` los descarga desde
  Hugging Face. Revisa esa licencia antes de redistribuir el modelo o un producto.
- El modelo de hablante incluido en KittenTTS 2 tiene términos MIT propios.
- Otras dependencias: PyTorch/torchaudio (BSD), Gradio (Apache-2.0), NumPy (BSD),
  soundfile (BSD), psutil (BSD), certifi (MPL-2.0), imageio-ffmpeg (BSD-2-Clause).
- La app escucha en `127.0.0.1` por defecto. No envíes audios ni textos a servicios
  externos: la generación es local.

Ver `THIRD_PARTY_NOTICES.md` para detalles y enlaces.
