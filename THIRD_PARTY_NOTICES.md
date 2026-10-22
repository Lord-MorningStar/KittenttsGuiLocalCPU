# Avisos de terceros

Este proyecto usa modelos y dependencias de terceros. Los pesos no se incluyen en
el repositorio: se descargan desde Hugging Face durante la instalación.

## Modelo KittenTTS 2

- Repositorio: https://huggingface.co/KittenML/kitten-tts-2
- Revisión: `1f00fee525c7b2e30bbe9ca9ba67529734fce9c9`
- Licencia de los pesos: **Stellon Labs Community License**
  (https://huggingface.co/KittenML/kitten-tts-2/blob/main/LICENSE.md)
- El paquete `kittenml` que carga el modelo usa **Apache-2.0**.
- El modelo de hablante `speaker/` incluido en el repositorio del modelo usa **MIT**
  (https://huggingface.co/KittenML/kitten-tts-2/blob/main/speaker/LICENSE).
- El código del motor C++ está en https://github.com/KittenML/kitten-tts-2-cpp.

La licencia comunitaria permite investigación, uso no comercial y uso comercial
limitado; el permiso comercial termina al superar USD 1.000.000 de ingresos anuales
o financiación acumulada. La redistribución de pesos, derivados o productos tiene
requisitos de atribución. Revisa el texto completo antes de redistribuir.

## Chatterbox Turbo (decodificador S3)

- Repositorio: https://huggingface.co/ResembleAI/chatterbox-turbo
- Revisión: `749d1c1a46eb10492095d68fbcf55691ccf137cd`
- Licencia: **MIT**
- Se descarga `s3gen_meanflow.safetensors` para la preparación de voces.

## Dependencias Python

| Paquete | Versión usada | Licencia |
|---|---|---|
| PyTorch (`torch`) | 2.13.0+cpu / 2.11.0+cpu | BSD-3-Clause |
| torchaudio | 2.11.0+cpu | BSD |
| Gradio | 6.30.0 | Apache-2.0 |
| kittenml | 0.9.6 | Apache-2.0 |
| kitten-tts-cpp | 0.2.0 | MIT |
| NumPy | 2.x | BSD-3-Clause |
| soundfile | 0.14.0 | BSD-3-Clause |
| psutil | 7.x | BSD-3-Clause |
| certifi | 2026.x | MPL-2.0 |
| imageio-ffmpeg | 0.6.0 | BSD-2-Clause |
| onnxruntime | 1.31.x | MIT |
| safetensors | 0.8.x | Apache-2.0 |
| huggingface_hub | 1.x / 2.x | Apache-2.0 |

Las licencias de las dependencias transitorias se conservan en sus paquetes
instalados dentro de `.venv-cpp` y `.venv-prep`.

## Marcas

KittenTTS, Stellon Labs, Resemble AI, Chatterbox, PyTorch, Gradio y los demás
nombres son marcas de sus respectivos titulares. Este proyecto no está afiliado
ni patrocinado por ellos.
