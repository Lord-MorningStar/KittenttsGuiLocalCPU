# Plan de implementación

## Hecho

- [x] Backend C++ para generación y Python aislado para preparar voces.
- [x] Descarga y ensamblado reproducible de assets.
- [x] Preparación de referencias de 6–30 s con S3Codec y SpeakerEncoder.
- [x] Cola de trabajos, historial y prueba automática de voces clonadas.
- [x] Interfaz Gradio local en español.
- [x] Scripts de instalación y arranque para Linux.
- [x] Scripts de instalación y arranque para Windows (pendientes de validar en Windows).
- [x] Diagnóstico y smoke tests.
- [x] Pruebas end-to-end en Linux/WSL: generación, clonación y app HTTP 200.
- [x] ZIP de distribución con código, scripts y documentación (sin pesos ni venvs).

## Pendiente

- [ ] Validar `setup.bat` y `run.bat` en Windows 10/11 real.
- [ ] Probar en hardware objetivo (i5-7200U, 12 GB RAM).
- [ ] Medir tiempos y memoria en Windows.
- [x] Limpiar artefactos de prueba antes de una distribución pública.
- [ ] Validar la licencia y la atribución con el texto definitivo de Stellon Labs.
