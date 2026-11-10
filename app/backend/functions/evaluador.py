"""
Validación y puntaje de las respuestas. TODO se decide aquí, nunca en el navegador.
(Las reglas de formato replican las de static/js/validadores.js.)
"""
import re

PONDERADORES_RUT = [2, 3, 4, 5, 6, 7]
PATRON_RUT = re.compile(r"^(\d{7,8})-([\dkK])$")
PATRON_CORREO = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
MAX_LARGO_TEXTO = 200

MSG_OBLIGATORIA = "Esta pregunta es obligatoria."
MSG_RUT = "Ingrese un RUT válido (sin puntos y con guión). Ej: 12345678-5"
MSG_EMAIL = "Ingrese un correo electrónico válido."
MSG_OPCION = "Seleccione una opción válida."
MSG_LARGO = f"La respuesta no puede superar los {MAX_LARGO_TEXTO} caracteres."


def rut_valido(valor):
    coincidencia = PATRON_RUT.match(valor)
    if not coincidencia:
        return False
    cuerpo, digito = coincidencia.groups()
    suma = sum(
        int(d) * PONDERADORES_RUT[i % len(PONDERADORES_RUT)]
        for i, d in enumerate(reversed(cuerpo))
    )
    resto = 11 - (suma % 11)
    esperado = "0" if resto == 11 else "K" if resto == 10 else str(resto)
    return esperado == digito.upper()


def _validar_informacion(pregunta, valor):
    if not isinstance(valor, str) or not valor.strip():
        return None, MSG_OBLIGATORIA
    valor = valor.strip()
    if len(valor) > MAX_LARGO_TEXTO:
        return None, MSG_LARGO
    regla = pregunta.get("validacion")
    if regla == "rut":
        if not rut_valido(valor):
            return None, MSG_RUT
        return valor.upper(), None
    if regla == "email" and not PATRON_CORREO.match(valor):
        return None, MSG_EMAIL
    return valor, None


def _validar_unica(pregunta, valor):
    if valor is None or valor == "":
        return None, MSG_OBLIGATORIA
    if not isinstance(valor, str) or valor not in pregunta["opciones"]:
        return None, MSG_OPCION
    return valor, None


def _validar_multiple(pregunta, valor):
    if not valor:
        return None, MSG_OBLIGATORIA
    if not isinstance(valor, list) or not all(isinstance(v, str) for v in valor):
        return None, MSG_OPCION
    if any(v not in pregunta["opciones"] for v in valor):
        return None, MSG_OPCION
    return list(dict.fromkeys(valor)), None  # sin repetidos, conserva el orden


VALIDADORES = {
    "informacion": _validar_informacion,
    "seleccion_unica": _validar_unica,
    "seleccion_multiple": _validar_multiple,
}


def validar_respuestas(formulario, respuestas):
    """
    Devuelve (limpias, errores).
      limpias  { id_pregunta: valor normalizado }
      errores  { id_pregunta: mensaje }  (vacío si todo está bien)
    """
    if not isinstance(respuestas, dict):
        return {}, {0: "Formato de respuestas inválido."}

    recibidas = {str(clave): valor for clave, valor in respuestas.items()}
    limpias, errores = {}, {}

    for seccion in formulario["secciones"]:
        for pregunta in seccion["preguntas"]:
            validar = VALIDADORES[pregunta["tipo"]]
            valor, error = validar(pregunta, recibidas.get(str(pregunta["id"])))
            if error:
                errores[pregunta["id"]] = error
            else:
                limpias[pregunta["id"]] = valor

    return limpias, errores


def _es_correcta(pregunta, respuesta):
    correcta = pregunta["correcta"]
    if isinstance(correcta, list):  # preparado para selección múltiple puntuada
        return isinstance(respuesta, list) and set(respuesta) == set(correcta)
    return respuesta == correcta


def calcular_puntaje(formulario, limpias):
    """
    Devuelve (puntaje, detalle, aprobado).
      detalle  { id_pregunta: True/False } solo de las preguntas con puntos
    """
    puntaje, detalle = 0, {}

    for seccion in formulario["secciones"]:
        for pregunta in seccion["preguntas"]:
            if not pregunta.get("puntos"):
                continue
            acierto = _es_correcta(pregunta, limpias.get(pregunta["id"]))
            detalle[pregunta["id"]] = acierto
            if acierto:
                puntaje += pregunta["puntos"]

    return puntaje, detalle, puntaje >= formulario["puntajeAprobacion"]
