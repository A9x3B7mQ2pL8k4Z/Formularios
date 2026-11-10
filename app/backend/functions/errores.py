"""
Registro de errores del programa y del envío a Make.

Cada error se guarda en tres lugares, para que ninguno dependa de otro:
  1. Redis (últimos MAX_ERRORES; consultables con GET /admin/errores).
  2. El webhook de errores de Make (MAKE_ERROR_WEBHOOK_URL), que agrega una fila al Excel de
     errores. El ID del error lo pone el propio Excel: aquí no se genera ni se envía.
  3. El log de Vercel, SIN datos personales (solo respuesta y descripción).

`registrar_error` NUNCA lanza excepciones: un fallo al registrar no puede romper la respuesta
al alumno ni provocar otro registro. Todo es síncrono: en Vercel un hilo en segundo plano se
congela apenas se responde.
"""
import json
import logging

from . import formato, webhook

MAX_DESCRIPCION = 500
CLAVES_CONDUCTOR = ("razon_social", "rut_razon_social", "nombre_conductor", "rut_conductor")
log = logging.getLogger("academia.errores")


def datos_conductor(formulario, limpias):
    """Razón social, RUT de la empresa, conductor y RUT del conductor, ya formateados ('' si faltan)."""
    try:
        valores, _ = webhook._por_campo(formulario, limpias)
    except Exception:  # formulario o respuestas incompletos: se registra sin datos
        return dict.fromkeys(CLAVES_CONDUCTOR, "")

    def texto(campo, formatear):
        valor = valores.get(campo)
        return formatear(valor) if isinstance(valor, str) and valor.strip() else ""

    return {
        "razon_social": texto(webhook.CAMPO_RAZON_SOCIAL, formato.texto_mayusculas),
        "rut_razon_social": texto(webhook.CAMPO_RUT_RAZON_SOCIAL, formato.rut),
        "nombre_conductor": texto(webhook.CAMPO_CONDUCTOR, formato.texto_mayusculas),
        "rut_conductor": texto(webhook.CAMPO_RUT_CONDUCTOR, formato.rut),
    }


def descripcion_de(excepcion):
    return f"{type(excepcion).__name__}: {excepcion}"


def armar_error(descripcion, contexto=None):
    """
    JSON del error (lo que recibe Make). `contexto` = {formulario, limpias, id_respuesta} o None
    si el error ocurrió antes de conocer al alumno: en ese caso esos campos van vacíos.
    """
    contexto = contexto or {}
    formulario, limpias = contexto.get("formulario"), contexto.get("limpias")
    registro = datos_conductor(formulario, limpias) if formulario and limpias else dict.fromkeys(CLAVES_CONDUCTOR, "")
    ahora = formato.ahora_santiago()
    return {
        "respuesta": contexto.get("id_respuesta") or "",
        "registro": registro,
        "descripcion": str(descripcion)[:MAX_DESCRIPCION],
        "fecha": f"{formato.fecha_atencion(ahora)} {ahora.strftime('%H:%M')}",
    }


def registrar_error(config, repositorio, descripcion, contexto=None):
    """Devuelve el error registrado (o None si ni siquiera pudo armarse). No lanza excepciones."""
    try:
        error = armar_error(descripcion, contexto)
    except Exception:
        log.exception("No se pudo armar el registro de error")
        return None

    # 1) Log de Vercel: sin RUT ni nombres.
    log.error("Error del programa o de Make | respuesta=%s | %s",
              error["respuesta"] or "-", error["descripcion"])

    # 2) Redis
    try:
        repositorio.guardar_error(error)
    except Exception:
        log.exception("No se pudo guardar el error en Redis")

    # 3) Make (Excel de errores)
    try:
        if config.MAKE_ERROR_WEBHOOK_URL:
            ok, motivo = webhook.publicar_json(
                config.MAKE_ERROR_WEBHOOK_URL, config.MAKE_ERROR_WEBHOOK_SECRET,
                error, config.ERROR_WEBHOOK_TIMEOUT_SEGUNDOS,
            )
            if not ok:
                log.error("El webhook de errores de Make falló: %s", motivo)
        elif not config.EN_PRODUCCION:
            print("\n[ERROR SIMULADO] MAKE_ERROR_WEBHOOK_URL vacío; se enviaría:")
            print(json.dumps(error, ensure_ascii=False, indent=2))
    except Exception:
        log.exception("No se pudo enviar el error a Make")
    return error

