## Context

El modo "Web Load" de la GUI de Moxfield actual solo simula la descarga de imágenes. Para implementar la descarga real de imágenes de Scryfall, debemos integrar la API de Scryfall de forma eficiente, implementar controles en la interfaz de usuario de Tkinter, aplicar un filtro de calidad de imagen para asegurar impresiones nítidas, y utilizar un sistema de caché local.

## Goals / Non-Goals

**Goals:**
- Implementar la descarga real de imágenes PNG de Scryfall con rate limiting (delays).
- Expandir la GUI de Tkinter para incluir:
  - Checkboxes excluyentes: "Usar edición exacta del mazo" y "Mejor imagen disponible".
  - Checkbox: "Preferir versión en Español".
  - Caja de texto para el umbral de calidad (por defecto: 100).
  - Checkboxes de zonas a descargar: Comandantes, Mazo Principal (ambos checked por defecto), Banquillo y Tokens (ambos unchecked por defecto).
- Desarrollar un filtro de calidad basado en la varianza del operador Laplaciano utilizando la librería `Pillow` (PIL) sin requerir OpenCV ni NumPy.
- Implementar almacenamiento estructurado por carpetas de mazo en `workdir/scryfall/<nombre_mazo>_<deck_id>/` y caché global en `workdir/scryfall_cache/`.
- Gestionar descargas de cartas de doble cara (DFCs) guardando ambos lados y evaluando la calidad de ambos.
- Reportar errores y crear un archivo `missing_cards.txt` en el directorio de salida del mazo al finalizar.

**Non-Goals:**
- Generar el PDF final a partir de las imágenes de Moxfield (esta funcionalidad está fuera del alcance de este cambio y se añadirá en versiones posteriores).
- Implementar traducción automática por procesamiento de imágenes (inpainting OpenCV y superposición de texto) debido a su complejidad y dependencias pesadas.
- Realizar web scraping sobre Wizards Gatherer como fallback (se limita estrictamente a la API de Scryfall y sus impresiones alternativas).

## Decisions

### 1. Motor de evaluación de calidad de imagen (Pillow vs. OpenCV)
- **Decisión:** Utilizar `Pillow` aplicando un filtro Laplaciano manual mediante `ImageFilter.Kernel` y obteniendo la varianza con `ImageStat.Stat`.
- **Razón:** OpenCV + NumPy aumentan el peso de la aplicación empaquetada con PyInstaller en unos ~100MB. Pillow ya es una dependencia del proyecto, por lo que su uso mantiene el tamaño del binario bajo y no requiere dependencias externas adicionales.
- **Alternativas consideradas:** OpenCV (`cv2`) con Laplacian variance. Rechazado por peso del instalador.

### 2. Estructura de nombres de archivos (`NombreCarta_SET_CN.png`)
- **Decisión:** Nombrar los archivos incluyendo el set y el número de coleccionista.
- **Razón:** Permite que coexistan múltiples impresiones diferentes de la misma carta (por ejemplo, tierras básicas con ilustraciones distintas) en el mismo directorio sin sobreescribirse mutuamente.
- **Alternativas consideradas:** Nombre simple (`NombreCarta.png`). Rechazado porque sobrescribe diferentes impresiones artísticas de una misma carta en el mazo.

### 3. Sistema de almacenamiento de descargas y caché global
- **Decisión:** Organizar descargas en carpetas por mazo (`workdir/scryfall/<nombre_mazo>_<deck_id>/`) y copiar archivos desde una caché centralizada (`workdir/scryfall_cache/`) si ya existen y cumplen los requisitos de calidad.
- **Razón:** Mantiene los mazos aislados para impresión directa, pero reduce la descarga repetida de tierras básicas y staples comunes por red.
- **Alternativas consideradas:** 
  - Carpeta compartida única para todo: Rechazada para mantener los mazos estructurados.
  - Sin caché centralizada: Rechazada por ineficiencia de red.

### 4. Descarga de cartas de doble cara (DFCs)
- **Decisión:** Descargar caras A y B como archivos separados (`_front.png` y `_back.png`) y utilizar el valor mínimo de calidad de ambas caras como calidad representativa de la carta. Ambas deben superar el umbral.
- **Razón:** Asegura que tanto el frente como el reverso de la carta impresa tengan la calidad adecuada para el PDF.
- **Alternativas consideradas:** Evaluar únicamente la cara frontal. Rechazada por el riesgo de imprimir reversos borrosos.

## Risks / Trade-offs

- **[Riesgo] Rate Limiting de Scryfall** $\rightarrow$ **Mitigación:** Introducir un delay obligatorio de 0.5 a 1.0 segundos mediante `time.sleep()` en cada petición HTTP, y manejar adecuadamente los reintentos automáticos.
- **[Diferencia de Escala en Pillow]** $\rightarrow$ **Mitigación:** Al recortar Pillow los valores a `[0, 255]`, la varianza obtenida tiene un rango menor que la de OpenCV. Se preconfigura el umbral por defecto a 100 (equivalente empírico a los 800 de OpenCV) y se permite su edición.
