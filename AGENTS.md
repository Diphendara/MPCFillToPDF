# Guía de contexto para agentes

Antes de cambiar código, leer `README.md`, `CLAUDE.md` y `docs/PROJECT_CONTEXT.md`.

## Verificación mínima

Desde la raíz del proyecto:

```powershell
python -m pytest tests/ --ignore=tests/test_downloader.py -m "not network" -q
python -m pytest tests/test_downloader.py -m "not network" -q
python -m ruff check .
python -m ruff format --check .
```

En esta máquina `python` puede no estar disponible fuera del entorno virtual; comprobar primero `.venv\Scripts\python.exe`.

## Reglas de trabajo

- Mantener separadas las capas `src` (dominio/pipeline), `gui` (Tkinter) y `cli` (adaptador de consola).
- No ejecutar llamadas de Tkinter desde el hilo trabajador; comunicar resultados mediante `queue.Queue`.
- Conservar el orden y emparejamiento por índice de las listas de frontales, traseras y flags de recorte.
- No confundir `quantity` del XML con los slots reales de `<fronts>`: el pipeline cuenta los slots.
- Probar cambios de PDF/cropper con las imágenes reales pequeñas de los tests, no solo con mocks.
- No incluir `config.json`, cachés, logs, PDFs ni artefactos de build en commits.

Para detalles de contratos, flujo y riesgos conocidos, consultar `docs/PROJECT_CONTEXT.md`.
Para localizar rápidamente los módulos y las pruebas de un cambio, consultar
`docs/CHANGE_GUIDE.md`.
