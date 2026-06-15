# Tutorial
Si buscas un tutorial mira aquí -> [https://github.com/Diphendara/MPCFillToPDF/wiki/Tutorial](https://github.com/Diphendara/MPCFillToPDF/wiki/1-%E2%80%90-Tutorial)

# Sugerencias, bugs etc
Puedes buscarme en twitter/bsky como @diphendara o abrirme una issue por github


# MPCFillToPDF

Convierte un archivo de proyecto de [MPCFill](https://mpcfill.com/) (XML) en un PDF listo para imprimir en una imprenta local (A4, 3×3 cartas por página, doble cara).

El XML de MPCFill referencia imágenes alojadas en Google Drive. Esta herramienta las descarga, les quita el sangrado de MPC, las recoloca con un sangrado en espejo de 1 mm y monta el PDF con líneas de corte y marcas de impresora.

---

## Clave de API de Google Drive (recomendado)

Las imágenes de los XMLs de MPCFill están alojadas en Google Drive. Sin configuración adicional, el programa las descarga usando `gdown` (peticiones anónimas), que puede recibir errores **429 — rate limit** al descargar muchas imágenes seguidas.

Para evitarlo, configura una **API Key de Google Drive** (gratuita, no requiere OAuth ni cuenta de servicio):

1. Ve a [Google Cloud Console](https://console.cloud.google.com/).
2. Crea un proyecto (o usa uno existente).
3. Activa la **Google Drive API** (Biblioteca → busca "Google Drive API" → Habilitar).
4. Ve a **Credenciales** → **Crear credenciales** → **Clave de API**.
5. (Opcional pero recomendado) Restringe la clave a la Google Drive API.
6. Copia el archivo `config.example.json` y renómbralo a `config.json`:
   ```
   cp config.example.json config.json
   ```
7. Abre `config.json` y pega tu clave:
   ```json
   {
     "google_drive_api_key": "AIza..."
   }
   ```

> **`config.json` está en `.gitignore` y nunca se sube al repositorio.**
> Si no configuras la clave, el programa sigue funcionando con `gdown` como antes.

---

## Instalación

### 1. Requisitos previos

- **Python 3.10 o superior** ([descarga oficial](https://www.python.org/downloads/)). Durante la instalación marca *"Add Python to PATH"*.
- **Git** (opcional, solo si clonas el repositorio).

Verifica:
```
python --version
```

### 2. Obtener el código

Clónalo:
```
git clone <url-del-repo> MPCFillToPDF
cd MPCFillToPDF
```

O descarga el ZIP del repositorio y descomprímelo.

### 3. Crear un entorno virtual (recomendado)

```
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # Linux/macOS
```

### 4. Instalar dependencias

```
pip install -r requirements.txt
```

Instala `Pillow`, `reportlab` y `gdown`.

---

## Uso

Hay dos formas: por línea de comandos (CLI) o con la interfaz gráfica (GUI).

### A) Línea de comandos (CLI)

1. Coloca tus archivos `.xml` de MPCFill en la carpeta `xml/` (en la raíz del proyecto). Puedes poner uno o varios.
2. Ejecuta:
   ```
   python -m cli.main
   ```
3. Los PDFs aparecen en una carpeta nueva por ejecución dentro de `out/`, con el nombre `DD_MM_YYYY_HH-MM-SS`. Cada PDF se nombra como el XML de origen:
   - `xml/mazo.xml` → `out/22_05_2026_14-30-12/out_mazo.pdf`
   - Si un PDF supera 500 MB se parte en `out_mazo_1.pdf`, `out_mazo_2.pdf`, … (el corte siempre cae tras una página de reversos para que cada parte siga siendo imprimible a doble cara).

#### Opciones de la CLI

| Opción         | Por defecto | Para qué sirve |
|----------------|-------------|----------------|
| `--xml-dir`    | `xml`       | Carpeta donde leer los `.xml`. |
| `--out-dir`    | `out`       | Carpeta donde escribir los PDFs. |
| `--workdir`    | `workdir`   | Carpeta para imágenes descargadas (`raw/`) e intermedias (`bled/`). |
| `--test`       | desactivado | **No** borra `workdir/raw` ni `workdir/bled` al terminar; útil para iterar sin volver a descargar y recortar. |
| `--yes` / `-y` | desactivado | Continuar sin pedir confirmación si alguna baraja no es múltiplo de 9. Útil para scripts. |

Ejemplos:
```
python -m cli.main
python -m cli.main --test
python -m cli.main --xml-dir mis_xmls --out-dir resultado
python -m cli.main -y                   # sin prompts
```

#### Ejemplo de ejecución

```
Encontrados 2 XML(s) en 'xml'.
Carpeta de salida: out\22_05_2026_14-30-12
  - mazo_a.xml: 95 cartas  (4 hueco(s) en blanco)
  - mazo_b.xml: 4 cartas  (5 hueco(s) en blanco)

Se fusionarán las siguientes barajas para evitar huecos en blanco:
  • mazo_a_mazo_b_union.pdf ← mazo_a.xml, mazo_b.xml  (99 cartas)

Procesando: mazo_a_mazo_b_union (fusión)
Descargando: [##############################] 89/89  ( 12.4s)
Recortando : [##############################] 89/89  (  6.1s)
Generando  : [##############################] 11/11  ( 88.2s)
  -> out\22_05_2026_14-30-12\out_mazo_a_mazo_b_union.pdf  (417.5 MB)

Resumen de fusiones escrito en: out\22_05_2026_14-30-12\resumen.txt
Tiempo total: 106.7s
```

### B) Interfaz gráfica (GUI)

Lanza la ventana:
```
python -m gui.main
```

Al iniciar la aplicación, se presenta una pantalla de bienvenida (**Launcher**) que permite seleccionar el modo de trabajo:

- **MPCFill (XML local)**: Ejecuta la aplicación de escritorio para procesar archivos XML locales de MPCFill.
- **Web Load (Moxfield)**: Ejecuta una ventana de diseño similar donde se gestiona la carga de mazos directamente desde Moxfield vía web.

### MPCFill (XML local)
- **Seleccionar XMLs…** abre el explorador para elegir uno o varios `.xml` (Ctrl+click para varios).
- **Vaciar** limpia la lista de proyectos en cola.
- **Imágenes locales (opcional)**: Permite añadir imágenes locales de traseras y frontales con opción de recortar bordes.

### Web Load (Moxfield)
- **Introduce la URL del mazo de Moxfield**: Un campo de texto directo donde pegar la URL y presionar **Cargar** para descargar y analizar el mazo.
- **Cartas Importadas (Moxfield)**: Muestra las cartas importadas del mazo desglosadas por zonas (Commanders, Mainboard, Sideboard, Tokens).
- **Configuración de Descarga**:
  - **Modo de descarga**:
    - *Usar edición exacta del mazo*: Descarga la edición exacta (set y número de coleccionista) especificada en el mazo de Moxfield.
    - *Mejor imagen disponible*: Busca y compara la calidad de todas las impresiones de la carta en Scryfall, seleccionando la de mayor resolución/nitidez.
    - *Preferir versión en Español*: Prioriza la descarga de la carta en español. Si no está disponible o no cumple con el umbral de calidad, busca alternativas en español y finalmente hace fallback a inglés.
  - **Zonas a descargar**: Permite seleccionar qué zonas del mazo descargar (Comandantes y Mazo Principal activos por defecto; Banquillo y Tokens inactivos por defecto).
  - **Umbral de calidad**: Permite establecer un umbral de calidad mínimo basado en la varianza del operador Laplaciano. Puedes elegir entre dos algoritmos:
    - *Pillow (por defecto)*: Calcula la varianza del Laplaciano usando enteros de 8 bits (con recorte de valores negativos a 0). El valor recomendado por defecto es **100**.
    - *OpenCV*: Calcula la varianza del Laplaciano con precisión doble de 64 bits sin recorte. El valor recomendado por defecto es **300**.
    Toggles con el checkbox "Usar algoritmo OpenCV", el cual actualiza automáticamente el valor del umbral según corresponda. Las imágenes por debajo de este umbral se descartan y se registran como faltantes.
- **Descargar imágenes de Scryfall**: Botón que descarga las imágenes reales de las cartas importadas en segundo plano desde Scryfall, aplicando el rate limit de la API (0.5s de delay), la caché global en `workdir/scryfall_cache/`, la comprobación de calidad utilizando el método seleccionado (Pillow o OpenCV) y generando un reporte `missing_cards.txt` en caso de fallos.
- **Limpiar Caché**: Abre un diálogo de opciones que permite eliminar selectivamente carpetas de caché y descargas temporales (`workdir/scryfall`, `workdir/scryfall_cache`, y/o `workdir/raw` y `workdir/bled`), previa confirmación.
- **Generar PDF con traseras / solo frontales**: Genera el archivo PDF listo para imprimir para el mazo de Moxfield y cualquier carta opcional añadida.
  - **Generar PDF con traseras**: Requiere al menos una imagen en la lista de **Traseras** del panel derecho para actuar como el reverso por defecto del mazo. Las cartas de doble cara (DFCs) usan de forma automática su trasera correspondiente de Scryfall (`_back.png`), y las cartas de una sola cara usan el reverso por defecto.
  - **Generar PDF solo frontales**: Genera el archivo PDF omitiendo las páginas traseras, sin necesidad de definir un reverso por defecto.
  - Las imágenes procedentes de Scryfall no se recortan por defecto (`crop_borders = False`), mientras que las imágenes locales opcionales del panel derecho respetan sus propios checkboxes de recorte de bordes.


### Controles Comunes (Panel Inferior)
- **Conservar caché**: si está marcado, no borra las imágenes descargadas (acelera futuras ejecuciones).
- **Estado + barra de progreso**: Informan del progreso actual.

Antes de generar:
- Si las barajas pueden **fusionarse** sin dejar huecos (suma múltiplo de 9), aparece un diálogo informativo con el plan.
- Si alguna baraja **dejará huecos** en su PDF, aparece un diálogo de advertencia *"¿Continuar de todos modos?"*.

Cuando termina, **se abre automáticamente la carpeta `out/`** en el Explorador.

### Empaquetar como `.exe` portable (Windows)

```
pip install pyinstaller
python build_exe.py
```

Genera `dist/MPCFillToPDF.exe`. El ejecutable es portable: en la carpeta donde lo dejes creará automáticamente `out/` y `workdir/` al ejecutarse por primera vez.

---

## Cómo se evita pagar páginas con huecos

La imprenta cobra cada A4 entera aunque no esté llena. Como cada página tiene 3×3 = 9 cartas, si el total no es múltiplo de 9 la última página queda con espacios vacíos pagados.

El sistema lo gestiona así:

1. **Cuenta las cartas** de cada XML antes de empezar.
2. **Si la suma de los XMLs *no múltiplos de 9*** sí es múltiplo de 9 → los fusiona en un único PDF llamado `<a>_<b>_..._union.pdf`. Cada carta conserva su reverso original.
3. **Si la suma sigue sin ser múltiplo de 9** → avisa de los huecos y pide confirmación.
4. Cuando hay fusiones, escribe **`resumen.txt`** dentro de la carpeta de la ejecución con el desglose:
   ```
   PDF: mazo_a_mazo_b_union.pdf  (99 cartas)
     - 95 carta(s) de mazo_a.xml
     - 4 carta(s) de mazo_b.xml
   ```

---

## Estructura del proyecto

```
MPCFillToPDF/
├── xml/                  ← .xml de MPCFill (modo CLI)
├── out/                  ← una subcarpeta por ejecución (DD_MM_YYYY_HH-MM-SS) con los PDFs y, si hay fusión, resumen.txt
├── workdir/              ← caché temporal: raw/ (descargas) y bled/ (recortes)
├── cli/main.py           ← entrada CLI
├── gui/
│   ├── main.py           ← entrada GUI (Tkinter)
│   └── paths.py          ← resolver out/ y workdir/ junto al .exe
├── src/
│   ├── parser.py         ← XML → estructura de cartas
│   ├── downloader.py     ← descarga desde Google Drive (gdown, 5 threads)
│   ├── cropper.py        ← quita bleed de MPC y añade espejo de 1 mm
│   ├── pdf_generator.py  ← maquetación + crop marks + barra de calibración
│   ├── pipeline.py       ← orquestador (run, run_merged)
│   ├── precheck.py       ← conteo, planificación de fusiones, manifiesto
│   └── assets/           ← imágenes embebidas (color_bar.png, corner_mark.png)
└── build_exe.py          ← script de empaquetado PyInstaller
```

## Formato del PDF generado

- A4 vertical, 3 columnas × 3 filas = 9 cartas por página.
- Carta: 63,5 × 88,9 mm (tamaño estándar MPC).
- Sangrado en espejo de 1 mm alrededor de cada carta.
- Página `n`: frentes en orden de slot (0–8, izquierda → derecha, arriba → abajo).
- Página `nB`: dorsos espejados horizontalmente para que el doble cara case.
- Líneas de corte 1 pt en los márgenes (no cruzan el interior).
- Marcas de registro en las 4 esquinas + barra CMYK arriba para calibración de imprenta.
- Numeración de pareja en la esquina inferior derecha: `1`, `1B`, `2`, `2B`, …
