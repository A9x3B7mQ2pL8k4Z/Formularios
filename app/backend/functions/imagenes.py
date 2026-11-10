"""
Imágenes de las preguntas: se optimizan (WebP, ancho máximo 800 px) y se suben a Vercel Blob.
Devuelve la URL pública, que el admin pone en `imagen.src` de la pregunta.
"""
import io
import uuid
from urllib.parse import urlsplit

import requests

ANCHO_MAXIMO = 800
FORMATOS_PERMITIDOS = {"PNG", "JPEG", "WEBP"}
BLOB_API = "https://blob.vercel-storage.com"
BLOB_API_VERSION = "13"


class ErrorImagen(Exception):
    def __init__(self, mensaje, codigo=400):
        super().__init__(mensaje)
        self.mensaje, self.codigo = mensaje, codigo


def es_url_blob_publica(valor):
    """Acepta URLs públicas de Blob, incluidos nombres escapados y subcarpetas."""
    if not isinstance(valor, str) or not valor or any(c.isspace() or ord(c) < 32 for c in valor):
        return False
    try:
        url = urlsplit(valor)
        host = url.hostname or ""
        sufijo = ".public.blob.vercel-storage.com"
        tienda = host.removesuffix(sufijo)
        return (
            url.scheme == "https" and host.endswith(sufijo)
            and bool(tienda) and all(c in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in tienda)
            and url.username is None and url.password is None and url.port in (None, 443)
            and url.path.startswith("/") and len(url.path) > 1 and not url.fragment
            and "\\" not in valor
        )
    except ValueError:
        return False


def optimizar(datos):
    """Devuelve (bytes_webp, ancho, alto). Rechaza lo que no sea PNG, JPG o WebP."""
    try:
        from PIL import Image, ImageOps
    except ImportError as error:  # pragma: no cover
        raise ErrorImagen("Falta Pillow en el servidor.", 501) from error

    Image.MAX_IMAGE_PIXELS = 25_000_000
    try:
        imagen = Image.open(io.BytesIO(datos))
        if imagen.format not in FORMATOS_PERMITIDOS:
            raise ErrorImagen("Formato no permitido: usa PNG, JPG o WebP.")
        imagen = ImageOps.exif_transpose(imagen)
        imagen.load()
    except ErrorImagen:
        raise
    except Exception as error:
        raise ErrorImagen("El archivo no es una imagen válida.") from error

    if imagen.width > ANCHO_MAXIMO:
        alto = max(1, round(imagen.height * ANCHO_MAXIMO / imagen.width))
        imagen = imagen.resize((ANCHO_MAXIMO, alto), Image.LANCZOS)
    if imagen.mode not in ("RGB", "RGBA"):
        imagen = imagen.convert("RGBA" if "A" in imagen.getbands() or "transparency" in imagen.info else "RGB")

    salida = io.BytesIO()
    imagen.save(salida, "WEBP", quality=80, method=4)
    return salida.getvalue(), imagen.width, imagen.height


def subir(config, datos):
    """Optimiza y sube la imagen. Devuelve {src, ancho, alto}."""
    if not config.BLOB_TOKEN:
        raise ErrorImagen("Falta BLOB_READ_WRITE_TOKEN: crea el Blob Store en Vercel.", 503)

    webp, ancho, alto = optimizar(datos)
    nombre = f"preguntas/{uuid.uuid4().hex}.webp"
    try:
        respuesta = requests.put(
            f"{BLOB_API}/",
            params={"pathname": nombre},
            data=webp,
            headers={
                "authorization": f"Bearer {config.BLOB_TOKEN}",
                "x-api-version": BLOB_API_VERSION,
                "x-vercel-blob-access": "public",
                "x-content-type": "image/webp",
                "x-add-random-suffix": "0",
                "x-cache-control-max-age": "31536000",
            },
            timeout=15,
        )
        respuesta.raise_for_status()
        url = respuesta.json()["url"]
        if not es_url_blob_publica(url):
            raise ValueError("Blob no devolvió una URL pública válida.")
    except (requests.RequestException, ValueError, KeyError) as error:
        raise ErrorImagen("No se pudo subir la imagen a Vercel Blob.", 502) from error
    return {"src": url, "ancho": ancho, "alto": alto}
