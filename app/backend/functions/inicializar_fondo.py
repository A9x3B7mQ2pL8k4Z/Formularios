"""Ejecuta: python -B -m app.backend.functions.inicializar_fondo.

Crea únicamente la clave del fondo con SET NX. Si existe una URL de fondo en
el entorno anterior, la migra. Nunca reemplaza una configuración ya guardada.
"""
import os

from .config import Config
from .imagenes import es_url_blob_publica
from .repositorio import ClienteUpstash, RepositorioRedis


def main():
    if not (Config.REDIS_URL and Config.REDIS_TOKEN):
        raise SystemExit("Faltan las credenciales de Redis en .env.")
    anterior = os.getenv("FONDO_FORMULARIOS_URL", "")
    if anterior and not es_url_blob_publica(anterior):
        raise SystemExit("La URL de fondo anterior no es una URL pública válida de Blob; no se modificó Redis.")
    repo = RepositorioRedis(ClienteUpstash(Config.REDIS_URL, Config.REDIS_TOKEN))
    creada = repo.inicializar_fondo(anterior)
    fondo = repo.obtener_fondo()
    print("Configuración creada." if creada else "La configuración ya existía; se conservó.")
    print("Fondo de Blob configurado." if fondo else "Sin imagen elegida: se mostrará el degradado hasta que el administrador seleccione un fondo.")
    print("Clave: " + repo.CLAVE_FONDO)


if __name__ == "__main__":
    main()
