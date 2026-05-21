from PIL import Image
import os

# Carpetas
input_folder = "imagenes_originales"
output_folder = "imagenes_recortadas"

# Crear carpeta de salida si no existe
os.makedirs(output_folder, exist_ok=True)

def calcular_recorte(ancho, alto):
    # Porcentajes estimados del patrón
    porcentaje_x = 0.042   # 4.2% de ancho
    porcentaje_y = 0.031   # 3.1% de alto

    borde_x = int(round(ancho * porcentaje_x))
    borde_y = int(round(alto * porcentaje_y))

    return borde_x, borde_y

# Obtener lista de imágenes
imagenes = [f for f in os.listdir(input_folder) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.tiff'))]
total_imagenes = len(imagenes)

# Procesar imágenes
for i, nombre_archivo in enumerate(imagenes, start=1):
    ruta_imagen = os.path.join(input_folder, nombre_archivo)
    imagen = Image.open(ruta_imagen)

    ancho, alto = imagen.size

    borde_x, borde_y = calcular_recorte(ancho, alto)

    # Definir la caja para recortar
    caja = (borde_x, borde_y, ancho - borde_x, alto - borde_y)
    imagen_recortada = imagen.crop(caja)

    # Guardar
    ruta_guardado = os.path.join(output_folder, nombre_archivo)
    imagen_recortada.save(ruta_guardado)

    print(f"{i}/{total_imagenes} - {nombre_archivo} ({ancho}x{alto}) → Recorte {borde_x}px, {borde_y}px → Final {imagen_recortada.size}")

print("Proceso completado.")
