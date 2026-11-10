"""Configuración leída desde variables de entorno (.env en local)."""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    if os.getenv("VERCEL") != "1":
        load_dotenv()
except ImportError:  # python-dotenv es opcional (en Vercel las variables ya vienen en el entorno)
    pass

RAIZ_PROYECTO = Path(__file__).resolve().parents[3]
CARPETA_FRONTEND = RAIZ_PROYECTO / "app" / "frontend"


class Config:
    # "desarrollo" (pruebas locales) o "produccion" (Vercel)
    APP_ENV = os.getenv("APP_ENV", "desarrollo")
    EN_PRODUCCION = APP_ENV == "produccion" or os.getenv("VERCEL") == "1"

    # Firma de los tokens. OBLIGATORIA en producción.
    SECRET_KEY = os.getenv("SECRET_KEY") or ("dev-clave-insegura-solo-local" if not EN_PRODUCCION else None)

    # Validez del token desde su emisión (5 días)
    TOKEN_TTL_SEGUNDOS = int(os.getenv("TOKEN_DIAS", os.getenv("TOKEN_TTL_DIAS", "5"))) * 24 * 60 * 60

    # Webhook de Make.com. Vacío = modo simulación (imprime el payload en consola)
    MAKE_WEBHOOK_URL = os.getenv("MAKE_WEBHOOK_URL", "")
    MAKE_WEBHOOK_SECRET = os.getenv("MAKE_WEBHOOK_SECRET", "")  # opcional, va en el header x-make-apikey
    WEBHOOK_TIMEOUT_SEGUNDOS = 8

    # Webhook de Make SOLO para errores (escenario aparte que agrega una fila al Excel de errores).
    # Opcional: vacío = el error queda únicamente en Redis y en el log de Vercel.
    MAKE_ERROR_WEBHOOK_URL = os.getenv("MAKE_ERROR_WEBHOOK_URL", "")
    MAKE_ERROR_WEBHOOK_SECRET = os.getenv("MAKE_ERROR_WEBHOOK_SECRET", "")
    ERROR_WEBHOOK_TIMEOUT_SEGUNDOS = 3  # corto: el alumno está esperando la respuesta

    # Base de datos de formularios: Upstash Redis (REST). Vercel puede inyectarlas con los
    # nombres KV_REST_API_*; se aceptan ambos.
    REDIS_URL = os.getenv("UPSTASH_REDIS_REST_URL") or os.getenv("KV_REST_API_URL", "")
    REDIS_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN") or os.getenv("KV_REST_API_TOKEN", "")

    # Clave del programa administrador (header X-Admin-Key). Vacía = API de admin deshabilitada.
    ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")

    # Imágenes de las preguntas (Vercel Blob). Solo hace falta para subir imágenes.
    BLOB_TOKEN = os.getenv("BLOB_READ_WRITE_TOKEN", "")

    MAX_ENVIO_BYTES = 64 * 1024  # tamaño máximo de un envío de respuestas (64 KB)
    MAX_CONTENT_LENGTH = 6 * 1024 * 1024  # tope general; el admin sube imágenes (Vercel limita a 4,5 MB)

    @classmethod
    def validar(cls):
        if cls.EN_PRODUCCION:
            if not cls.SECRET_KEY:
                raise RuntimeError("Falta SECRET_KEY (obligatoria en producción).")
            if not cls.MAKE_WEBHOOK_URL:
                raise RuntimeError("Falta MAKE_WEBHOOK_URL (obligatoria en producción).")
            if not (cls.REDIS_URL and cls.REDIS_TOKEN):
                raise RuntimeError(
                    "Faltan UPSTASH_REDIS_REST_URL y UPSTASH_REDIS_REST_TOKEN "
                    "(la base de datos de formularios es obligatoria en producción)."
                )
            if len(cls.ADMIN_API_KEY) < 24:
                raise RuntimeError("Falta ADMIN_API_KEY (mínimo 24 caracteres) para la API de administración.")
        if cls.TOKEN_TTL_SEGUNDOS <= 0:
            raise RuntimeError("TOKEN_DIAS debe ser mayor que cero.")
