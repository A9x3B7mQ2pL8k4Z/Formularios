"""Envío de resultados al webhook de Make.com."""
import json

import requests

from . import certificados, formato

# campo del formulario (primera sección) que alimenta cada clave de `registro`.
# Todos los formularios deben traerlos (lo exige esquema.py).
CAMPO_RAZON_SOCIAL = "razon_social"
CAMPO_RUT_RAZON_SOCIAL = "rut_empresa"
CAMPO_CONDUCTOR = "nombre"
CAMPO_RUT_CONDUCTOR = "rut"
CAMPO_EMAIL = "email"
CAMPO_CHASIS = "chasis"
CAMPO_MODELO = "modelo"
CAMPO_POTENCIA = "potencia"
CAMPO_TRACCION = "traccion"
CAMPO_ANIO_COMERCIAL = "anio"
CAMPO_INSTRUCTOR = "instructor"

CAMPOS_REGISTRO = (
    CAMPO_RAZON_SOCIAL, CAMPO_RUT_RAZON_SOCIAL, CAMPO_CONDUCTOR, CAMPO_RUT_CONDUCTOR,
    CAMPO_EMAIL, CAMPO_CHASIS, CAMPO_MODELO, CAMPO_POTENCIA, CAMPO_TRACCION, CAMPO_ANIO_COMERCIAL, CAMPO_INSTRUCTOR,
)


def _por_campo(formulario, limpias):
    """({campo: valor respondido}, {campo: opciones}) de la primera sección."""
    valores, opciones = {}, {}
    for pregunta in formulario["secciones"][0]["preguntas"]:
        campo = pregunta.get("campo")
        if campo:
            valores[campo] = limpias.get(pregunta["id"])
            opciones[campo] = pregunta.get("opciones", [])
    return valores, opciones


def armar_payload(formulario, limpias, puntaje, id_respuesta, ahora=None, id_certificado=None, duplicado=0):
    """
    JSON para Make:
      respuesta     ID de la respuesta ("P1-7": prueba 1, respuesta 7 de su hoja)
      formulario_id número del formulario (1, 2, 3...); el UUID del QR no viaja a Make
      puntuacion    puntaje obtenido
      duplicado     0 o 1; solo marca duplicados de certificados de 100 puntos
      registro      datos ya formateados (ver formato.py)
      certificado   PDF en Base64 si puntuacion == 100; None en los demás casos
    """
    valores, opciones = _por_campo(formulario, limpias)
    faltan = [c for c in CAMPOS_REGISTRO if valores.get(c) in (None, "", [])]
    if faltan:
        raise ValueError(f"El formulario no tiene los campos requeridos: {', '.join(faltan)}")

    ahora = ahora or formato.ahora_santiago()  # una sola lectura: fecha, mes y año siempre coinciden
    payload = {
        "respuesta": id_respuesta,
        "formulario_id": formulario["numero"],
        "puntuacion": puntaje,
        "duplicado": int(bool(duplicado)),
        "registro": {
            "razon_social": formato.texto_mayusculas(valores[CAMPO_RAZON_SOCIAL]),
            "rut_razon_social": formato.rut(valores[CAMPO_RUT_RAZON_SOCIAL]),
            "nombre_conductor": formato.texto_mayusculas(valores[CAMPO_CONDUCTOR]),
            "rut_conductor": formato.rut(valores[CAMPO_RUT_CONDUCTOR]),
            "email": valores[CAMPO_EMAIL],
            "chasis": valores[CAMPO_CHASIS],
            "puntaje": puntaje,
            "modelo": formato.unir_modelos(valores[CAMPO_MODELO], opciones[CAMPO_MODELO]),
            "potencia": formato.unir_potencias(valores[CAMPO_POTENCIA]),
            "traccion": formato.unir_tracciones(valores[CAMPO_TRACCION]),
            "anio_comercial": formato.unir_anios(valores[CAMPO_ANIO_COMERCIAL]),
            "fecha_atencion": formato.fecha_atencion(ahora),
            "mes": formato.mes(ahora),
            "anio": ahora.year,
            "instructor": formato.texto_mayusculas(valores[CAMPO_INSTRUCTOR]),
        },
    }
    payload["certificado"] = (
        None if payload['duplicado'] else certificados.crear_adjunto(payload, formulario["titulo"], id_certificado)
    )
    return payload


def publicar_json(url, secreto, payload, timeout):
    """POST JSON a un webhook de Make. Devuelve (ok, motivo); `motivo` describe el fallo (sin datos personales)."""
    cabeceras = {"Content-Type": "application/json"}
    if secreto:
        cabeceras["x-make-apikey"] = secreto
    try:
        respuesta = requests.post(url, json=payload, headers=cabeceras, timeout=timeout)
        respuesta.raise_for_status()
        return True, None
    except requests.Timeout:
        return False, f"Make no respondió en {timeout} s (timeout)"
    except requests.HTTPError as error:
        return False, f"Make respondió con error HTTP {error.response.status_code}"
    except requests.RequestException as error:
        return False, f"No se pudo conectar con Make ({type(error).__name__})"


def enviar(config, payload):
    """
    Devuelve (ok, motivo). `ok` es True si el webhook respondió OK (o si está en modo
    simulación en desarrollo); si no, `motivo` dice por qué.
    """
    if not config.MAKE_WEBHOOK_URL:
        if config.EN_PRODUCCION:
            return False, "MAKE_WEBHOOK_URL vacío"
        print("\n[WEBHOOK SIMULADO] MAKE_WEBHOOK_URL vacío; payload que se enviaría:")
        vista = dict(payload)
        if payload.get("certificado"):
            adjunto = payload["certificado"]
            vista["certificado"] = {
                **adjunto,
                "contenido_base64": f"<{len(adjunto['contenido_base64'])} caracteres Base64 omitidos en consola>",
            }
        print(json.dumps(vista, ensure_ascii=False, indent=2))
        return True, None

    ok, motivo = publicar_json(
        config.MAKE_WEBHOOK_URL, config.MAKE_WEBHOOK_SECRET, payload, config.WEBHOOK_TIMEOUT_SEGUNDOS
    )
    if not ok:
        print(f"[WEBHOOK] Falló el envío a Make: {motivo}")
    return ok, motivo
