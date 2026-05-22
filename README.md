# MPCFillToPDF

Convierte un archivo de proyecto de [MPCFill](https://mpcfill.com/) (XML) en un PDF listo para imprimir en una imprenta local (a doble cara, A4, 3×3 cartas por página).

El XML de MPCFill referencia imágenes alojadas en Google Drive. Esta herramienta las descarga, les quita el sangrado de MPC, las recoloca con un sangrado en espejo de 1 mm y monta el PDF con líneas de corte.

## Requisitos

- Python 3.10 o superior
- Dependencias: `pip install -r requirements.txt`

## Cómo usarlo

Hay dos formas:

### A) Interfaz gráfica (GUI)

```
python -m gui.main
```

Aparece una ventana con un botón **Seleccionar XMLs…**, una lista con los archivos en cola, una casilla **Conservar caché**, y un botón **Generar PDF(s)**. Cuando termina, abre automáticamente la carpeta `out/`.

Para empaquetar como **.exe portable** (Windows):

```
pip install pyinstaller
python build_exe.py
```

Genera `dist/MPCFillToPDF.exe`. El ejecutable es portable: en la carpeta donde lo dejes creará automáticamente `out/` y `workdir/` al ejecutarse.

### B) Línea de comandos (CLI)

1. **Coloca los XML en la carpeta `xml/`** (en la raíz del proyecto). Puedes poner uno o varios; se procesarán todos.
2. **Ejecuta el comando**:
   ```
   python -m cli.main
   ```
3. **Recoge los PDFs en `out/`**. Cada PDF se nombra como el XML de origen:
   - `xml/mazo.xml` → `out/mazo.pdf`
   - Si el PDF supera 500 MB, se parte en `out/mazo_1.pdf`, `out/mazo_2.pdf`, … (el corte siempre se hace tras una página de reversos, así cada parte sigue siendo imprimible a doble cara).

### Estructura de carpetas

```
MPCFillToPDF/
├── xml/         ← pon aquí tus .xml de MPCFill (modo CLI)
├── out/         ← aquí aparecen los PDFs generados
├── workdir/     ← caché temporal (descargas y recortes); opcionalmente se borra al terminar
├── cli/         ← entrada CLI
├── gui/         ← entrada GUI (Tkinter)
└── src/         ← pipeline (parser, downloader, cropper, pdf_generator)
```

### Opciones del CLI

| Opción       | Por defecto | Para qué sirve                                                                          |
|--------------|-------------|-----------------------------------------------------------------------------------------|
| `--xml-dir`  | `xml`       | Carpeta de la que se leen los `.xml`.                                                   |
| `--out-dir`  | `out`       | Carpeta donde se escriben los PDFs.                                                     |
| `--workdir`  | `workdir`   | Carpeta para imágenes descargadas (`raw/`) e intermedias (`bled/`).                     |
| `--test`     | desactivado | **No** borra `workdir/raw` ni `workdir/bled` al terminar; útil para iterar sin volver a descargar y recortar todas las imágenes. |

Ejemplo:
```
python -m cli.main --test
python -m cli.main --xml-dir mis_xmls --out-dir resultado
```

## Progreso durante la ejecución

Mientras el proceso corre, se muestra una barra de progreso con cronómetro para cada etapa:

```
Procesando: mazo.xml
Descargando: [##############################] 42/42  ( 18.3s)
Recortando : [##############################] 42/42  (  6.1s)
Generando  : [##############################]  5/5   (  2.4s)
  -> out\mazo.pdf  (38.4 MB)

Tiempo total: 27.1s
Imágenes temporales (workdir/raw y workdir/bled) eliminadas.
```

## Limpieza automática

Al terminar, `workdir/raw` (originales descargados) y `workdir/bled` (recortados con sangrado) se borran para liberar espacio.

Si quieres conservarlos (por ejemplo, para volver a generar el PDF sin re-descargar 200 MB de imágenes), añade `--test`:

```
python -m cli.main --test
```

En modo `--test` la caché de Google Drive y los recortes se mantienen. La siguiente ejecución los reutilizará automáticamente (el `downloader` salta cualquier archivo ya presente).

## Formato del PDF generado

- A4 vertical, 3 columnas × 3 filas = 9 cartas por página.
- Carta: 63,5 × 88,9 mm (tamaño estándar MPC).
- Sangrado en espejo de 1 mm alrededor de cada carta.
- Página 1: frentes en orden de slot (0–8, izquierda → derecha, arriba → abajo).
- Página 2: dorsos espejados horizontalmente para que el doble cara case.
- Líneas de corte finas (0,5 pt) en los márgenes y entre cartas.
