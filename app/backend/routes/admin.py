"""
API de administración (para el programa que crea, edita y borra formularios).

Todas las rutas exigen la clave `ADMIN_API_KEY` en el header `X-Admin-Key`.
El administrador envía el formulario SIN ids de pregunta: el backend los genera
(`P<numero>-<n>`) según el orden en que vienen las preguntas.

  GET    /admin/formularios                lista resumida
  GET    /admin/formularios/<codigo>       formulario completo (con respuestas correctas e ids)
  POST   /admin/formularios                crea (codigo opcional; si no, se genera uno de 10 caracteres)
  PUT    /admin/formularios/<codigo>       reemplaza el contenido (conserva codigo y numero)
  DELETE /admin/formularios/<codigo>       elimina
  POST   /admin/imagenes                   sube una imagen (multipart, campo `archivo`) a Vercel Blob
  GET    /admin/fondo                      URL del fondo actual
  PUT    /admin/fondo                      elige fondo con JSON {"src": "URL pública de Blob"}
  DELETE /admin/fondo                      vuelve al degradado
  GET    /admin/errores                    últimos errores (?limite=100)
"""
import hmac

from flask import Blueprint, jsonify, request

from ..functions import esquema, imagenes
from ..functions.repositorio import FormularioExistente, codigo_valido
from . import acceso

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

MAX_IMAGEN_BYTES = 4 * 1024 * 1024


def _error(mensaje, codigo, **extra):
    return jsonify({"error": mensaje, **extra}), codigo


def _clave_recibida():
    cabecera = request.headers.get("Authorization", "")
    if cabecera.startswith("Bearer "):
        return cabecera[7:].strip()
    return request.headers.get("X-Admin-Key", "")


@admin_bp.before_request
def exigir_clave():
    esperada = acceso.config().ADMIN_API_KEY
    if not esperada:
        return _error("API de administración deshabilitada: falta ADMIN_API_KEY.", 503)
    if not hmac.compare_digest(_clave_recibida().encode(), esperada.encode()):
        return _error("Clave de administrador inválida.", 401)


def _url_acceso(codigo):
    return f"{request.host_url}?f={codigo}"


def _resumen(formulario):
    return {
        "codigo": formulario["id"],
        "numero": formulario["numero"],
        "titulo": formulario["titulo"],
        "preguntas": sum(len(s["preguntas"]) for s in formulario["secciones"]),
        "puntajeTotal": formulario["puntajeTotal"],
        "puntajeAprobacion": formulario["puntajeAprobacion"],
        "url_qr": _url_acceso(formulario["id"]),
    }


@admin_bp.get("/formularios")
def listar():
    repo = acceso.repositorio()
    formularios = [repo.obtener(codigo) for codigo in repo.listar()]
    resumenes = [_resumen(f) for f in formularios if f]
    return jsonify(sorted(resumenes, key=lambda r: r["numero"]))


@admin_bp.get("/formularios/<codigo>")
def leer(codigo):
    formulario = acceso.repositorio().obtener(codigo)
    if formulario is None:
        return _error("Formulario no encontrado.", 404)
    return jsonify({**formulario, "url_qr": _url_acceso(codigo)})


@admin_bp.post("/formularios")
def crear():
    cuerpo = request.get_json(silent=True)
    codigo = cuerpo.pop("codigo", None) if isinstance(cuerpo, dict) else None
    if codigo is not None and not codigo_valido(codigo):
        return _error("codigo inválido: minúsculas, números, guion y guion bajo (máx. 64).", 422)

    definicion, errores = esquema.validar_definicion(cuerpo)
    if errores:
        return _error("El formulario tiene errores.", 422, errores=errores)

    repo = acceso.repositorio()
    try:
        codigo, numero = repo.crear(definicion, codigo)
    except FormularioExistente:
        return _error("Ya existe un formulario con ese código.", 409)
    return jsonify({"codigo": codigo, "numero": numero, "url_qr": _url_acceso(codigo),
                    "formulario": repo.obtener(codigo)}), 201


@admin_bp.put("/formularios/<codigo>")
def reemplazar(codigo):
    cuerpo = request.get_json(silent=True)
    if isinstance(cuerpo, dict):
        cuerpo.pop("codigo", None)
    definicion, errores = esquema.validar_definicion(cuerpo)
    if errores:
        return _error("El formulario tiene errores.", 422, errores=errores)

    repo = acceso.repositorio()
    if not repo.guardar(codigo, definicion):
        return _error("Formulario no encontrado.", 404)
    return jsonify(repo.obtener(codigo))


@admin_bp.delete("/formularios/<codigo>")
def eliminar(codigo):
    if not acceso.repositorio().eliminar(codigo):
        return _error("Formulario no encontrado.", 404)
    return jsonify({"eliminado": codigo})


@admin_bp.post("/imagenes")
def subir_imagen():
    archivo = request.files.get("archivo")
    if archivo is None:
        return _error("Envía la imagen en el campo `archivo` (multipart/form-data).", 400)
    datos = archivo.read(MAX_IMAGEN_BYTES + 1)
    if len(datos) > MAX_IMAGEN_BYTES:
        return _error("La imagen supera los 4 MB.", 413)
    try:
        return jsonify(imagenes.subir(acceso.config(), datos)), 201
    except imagenes.ErrorImagen as error:
        return _error(error.mensaje, error.codigo)


@admin_bp.get("/errores")
def listar_errores():
    try:
        limite = min(max(int(request.args.get("limite", 100)), 1), 1000)
    except ValueError:
        return _error("limite debe ser un número.", 400)
    repo = acceso.repositorio()
    return jsonify({"errores": repo.listar_errores(limite)})


@admin_bp.get("/fondo")
def leer_fondo():
    return jsonify({"src": acceso.repositorio().obtener_fondo()})


@admin_bp.put("/fondo")
def cambiar_fondo():
    cuerpo = request.get_json(silent=True)
    src = cuerpo.get("src") if isinstance(cuerpo, dict) else None
    if not imagenes.es_url_blob_publica(src):
        return _error("src debe ser una URL pública HTTPS de Vercel Blob.", 422)
    acceso.repositorio().guardar_fondo(src)
    return jsonify({"src": src})


@admin_bp.delete("/fondo")
def quitar_fondo():
    acceso.repositorio().guardar_fondo("")
    return jsonify({"src": ""})
