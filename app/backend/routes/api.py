"""
API JSON. Todas las rutas exigen un token vigente para el formulario de la URL.

  GET  /api/formularios/<id>          formulario SIN respuestas correctas
  POST /api/formularios/<id>/enviar   valida, puntúa, manda a Make y devuelve el resultado
"""
from flask import Blueprint, g, jsonify, request

from ..functions import errores as registro_errores
from ..functions import duplicados, evaluador, webhook
from ..functions.repositorio import formulario_publico
from . import acceso

api_bp = Blueprint("api", __name__, url_prefix="/api")


def _error(mensaje, codigo, **extra):
    return jsonify({"error": mensaje, **extra}), codigo


def _obtener_formulario_autorizado(id_formulario):
    """Devuelve (formulario, None) o (None, respuesta_de_error)."""
    if not acceso.acceso_valido(id_formulario):
        return None, _error("Acceso inválido o expirado. Escanea el QR nuevamente.", 401)
    formulario = acceso.repositorio().obtener(id_formulario)
    if formulario is None:
        return None, _error("Formulario no encontrado.", 404)
    return formulario, None


@api_bp.get("/formularios/<id_formulario>")
def obtener_formulario(id_formulario):
    formulario, error = _obtener_formulario_autorizado(id_formulario)
    if error:
        return error
    return jsonify(formulario_publico(formulario))


@api_bp.post("/formularios/<id_formulario>/enviar")
def enviar_respuestas(id_formulario):
    # Desde aquí, cualquier error no controlado se registra (ver manejadores en backend/__init__.py).
    # `g.envio` se va completando para saber a qué alumno y respuesta corresponde el error.
    g.envio = {}
    formulario, error = _obtener_formulario_autorizado(id_formulario)
    if error:
        return error

    cuerpo = request.get_json(silent=True)
    if not isinstance(cuerpo, dict) or "respuestas" not in cuerpo:
        return _error("Solicitud inválida.", 400)

    limpias, errores = evaluador.validar_respuestas(formulario, cuerpo["respuestas"])
    if errores:
        return _error("Hay respuestas inválidas.", 422, errores=errores)

    g.envio.update(formulario=formulario, limpias=limpias)
    puntaje, detalle, aprobado = evaluador.calcular_puntaje(formulario, limpias)

    # ID único de la respuesta: P<prueba>-<n>, con n del contador atómico del formulario.
    n = acceso.repositorio().siguiente_numero_respuesta(formulario["numero"])
    id_respuesta = f"P{formulario['numero']}-{n}"
    g.envio["id_respuesta"] = id_respuesta

    huella, propietario, duplicado = None, None, 0
    repo = acceso.repositorio()
    if puntaje == 100:
        huella = duplicados.crear_huella(formulario, limpias)
        estado, propietario = repo.huellas.reservar(huella)
        if estado == 'pendiente':
            return _error('Hay un envío en proceso. Espera unos segundos y vuelve a intentarlo.', 409)
        duplicado = int(estado == 'enviado')

    envio_iniciado = False
    try:
        id_certificado = repo.siguiente_numero_certificado() if puntaje == 100 and not duplicado else None
        payload = webhook.armar_payload(
            formulario, limpias, puntaje, id_respuesta,
            id_certificado=id_certificado, duplicado=duplicado,
        )
        envio_iniciado = True
        enviado, motivo = webhook.enviar(acceso.config(), payload)
        if propietario:
            if enviado and acceso.config().MAKE_WEBHOOK_URL:
                repo.huellas.confirmar(huella, propietario)
            else:
                # Un envío fallido o simulado no cuenta como certificado recibido.
                repo.huellas.liberar(huella, propietario)
    except Exception:
        # Si Make pudo recibirlo, conservar la reserva hasta que venza.
        if propietario and not envio_iniciado:
            repo.huellas.liberar(huella, propietario)
        raise
    if not enviado:
        # Make devolvió un error o no confirmó recepción: se notifica al webhook de errores.
        registro_errores.registrar_error(
            acceso.config(), acceso.repositorio(), f"No se pudo enviar a Make: {motivo}",
            contexto=g.envio,
        )

    return jsonify({
        "puntaje": puntaje,
        "aprobado": aprobado,
        "detalle": detalle,
        "enviado": enviado,
        "duplicado": False,  # nunca se informa duplicado al usuario (ver duplicados.py)
    })
