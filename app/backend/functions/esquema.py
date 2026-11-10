"""
Validación de la definición de un formulario que envía el administrador.

Solo pasa lo que está en la lista blanca: cualquier otra clave (incluido un `id`
escrito a mano) se descarta, porque los IDs los genera el backend.
Devuelve (definicion_limpia, errores). Si `errores` no está vacío, no se guarda nada.
"""
import re

from . import formato, webhook, imagenes

TIPOS = ("informacion", "seleccion_unica", "seleccion_multiple")
TIPOS_CON_OPCIONES = ("seleccion_unica", "seleccion_multiple")
VALIDACIONES = ("rut", "email")

PATRON_CAMPO = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
PATRON_IMAGEN = re.compile(r"/static/img/[\w.\-]+")

MAX_SECCIONES = 20
MAX_PREGUNTAS = 100
MAX_OPCIONES = 12


def _texto(valor, maximo, obligatorio=True):
    if not isinstance(valor, str) or (obligatorio and not valor.strip()):
        return None
    valor = valor.strip()
    return valor if len(valor) <= maximo else None


def _entero(valor, minimo, maximo):
    if isinstance(valor, bool) or not isinstance(valor, int):
        return None
    return valor if minimo <= valor <= maximo else None


def _validar_imagen(imagen, ruta, errores):
    if not isinstance(imagen, dict):
        errores.append(f"{ruta}: debe ser un objeto con src, alt, ancho y alto.")
        return None
    src = imagen.get("src")
    ancho = _entero(imagen.get("ancho"), 1, 4000)
    alto = _entero(imagen.get("alto"), 1, 4000)
    alt = _texto(imagen.get("alt"), 200, obligatorio=False)
    if not isinstance(src, str) or not (PATRON_IMAGEN.fullmatch(src) or imagenes.es_url_blob_publica(src)):
        errores.append(f"{ruta}.src: debe ser /static/img/<archivo> o una URL de Vercel Blob (https://....public.blob.vercel-storage.com/...).")
    if ancho is None or alto is None:
        errores.append(f"{ruta}: ancho y alto deben ser enteros entre 1 y 4000.")
    if alt is None:
        errores.append(f"{ruta}.alt: debe ser texto (máx. 200 caracteres).")
    return {"src": src, "alt": alt, "ancho": ancho, "alto": alto}


def _validar_pregunta(pregunta, ruta, es_primera_seccion, errores):
    if not isinstance(pregunta, dict):
        errores.append(f"{ruta}: debe ser un objeto.")
        return None

    limpia = {}
    tipo = pregunta.get("tipo")
    if tipo not in TIPOS:
        errores.append(f"{ruta}.tipo: debe ser uno de {', '.join(TIPOS)}.")
        return None
    limpia["tipo"] = tipo

    titulo = _texto(pregunta.get("titulo"), 1000)
    if titulo is None:
        errores.append(f"{ruta}.titulo: obligatorio (máx. 1000 caracteres).")
    limpia["titulo"] = titulo

    if tipo in TIPOS_CON_OPCIONES:
        opciones = pregunta.get("opciones")
        valido = (
            isinstance(opciones, list)
            and 2 <= len(opciones) <= MAX_OPCIONES
            and all(_texto(o, 300) for o in opciones)
            and len({o.strip() for o in opciones}) == len(opciones)
        )
        if not valido:
            errores.append(f"{ruta}.opciones: entre 2 y {MAX_OPCIONES} textos distintos y no vacíos.")
            opciones = None
        else:
            opciones = [o.strip() for o in opciones]
        limpia["opciones"] = opciones
    elif pregunta.get("opciones"):
        errores.append(f"{ruta}.opciones: las preguntas de tipo informacion no llevan opciones.")

    if "validacion" in pregunta and pregunta["validacion"] is not None:
        if tipo != "informacion" or pregunta["validacion"] not in VALIDACIONES:
            errores.append(f"{ruta}.validacion: solo en preguntas de informacion, valores {', '.join(VALIDACIONES)}.")
        else:
            limpia["validacion"] = pregunta["validacion"]

    # `campo` = nombre con el que viaja a Make. Obligatorio en la primera sección.
    campo = pregunta.get("campo")
    if campo is not None and not (isinstance(campo, str) and PATRON_CAMPO.match(campo)):
        errores.append(f"{ruta}.campo: minúsculas, números y guion bajo; empieza con letra (máx. 40).")
    elif es_primera_seccion and campo is None:
        errores.append(f"{ruta}.campo: obligatorio en la primera sección (es el nombre del dato que recibe Make).")
    if campo is not None:
        limpia["campo"] = campo

    if pregunta.get("imagen") is not None:
        limpia["imagen"] = _validar_imagen(pregunta["imagen"], f"{ruta}.imagen", errores)

    if pregunta.get("puntos") is not None:
        puntos = _entero(pregunta["puntos"], 1, 100)
        if puntos is None or tipo == "informacion":
            errores.append(f"{ruta}.puntos: entero de 1 a 100, solo en preguntas de selección.")
        else:
            limpia["puntos"] = puntos
            _validar_correcta(pregunta, limpia, ruta, errores)

    return limpia


def _validar_correcta(pregunta, limpia, ruta, errores):
    correcta, opciones = pregunta.get("correcta"), limpia.get("opciones") or []
    if limpia["tipo"] == "seleccion_unica":
        if not isinstance(correcta, str) or correcta.strip() not in opciones:
            errores.append(f"{ruta}.correcta: debe ser exactamente una de las opciones.")
            return
        limpia["correcta"] = correcta.strip()
    else:
        valido = (
            isinstance(correcta, list) and correcta
            and all(isinstance(c, str) and c.strip() in opciones for c in correcta)
        )
        if not valido:
            errores.append(f"{ruta}.correcta: lista no vacía con opciones existentes.")
            return
        limpia["correcta"] = list(dict.fromkeys(c.strip() for c in correcta))


def _validar_campos_registro(primera_seccion, errores):
    """
    La primera sección debe traer los datos que arma el JSON de Make (ver webhook.CAMPOS_REGISTRO)
    y sus opciones deben poder formatearse (formato.py): así un formulario mal hecho se rechaza
    al crearlo y no al primer envío de un alumno.
    """
    por_campo = {p["campo"]: p for p in primera_seccion["preguntas"] if p.get("campo")}
    faltan = [c for c in webhook.CAMPOS_REGISTRO if c not in por_campo]
    if faltan:
        errores.append(f"secciones[0]: faltan los campos obligatorios para Make: {', '.join(faltan)}.")

    for campo in (webhook.CAMPO_RUT_CONDUCTOR, webhook.CAMPO_RUT_RAZON_SOCIAL):
        p = por_campo.get(campo)
        if p and (p["tipo"] != "informacion" or p.get("validacion") != "rut"):
            errores.append(f"campo '{campo}': debe ser de tipo informacion con validacion 'rut'.")
    for campo in (webhook.CAMPO_CONDUCTOR, webhook.CAMPO_RAZON_SOCIAL, webhook.CAMPO_CHASIS):
        p = por_campo.get(campo)
        if p and p["tipo"] != "informacion":
            errores.append(f"campo '{campo}': debe ser de tipo informacion.")

    p = por_campo.get(webhook.CAMPO_EMAIL)
    if p and (p["tipo"] != "informacion" or p.get("validacion") != "email"):
        errores.append("campo 'email': debe ser de tipo informacion con validacion 'email'.")

    convertidores = {
        webhook.CAMPO_MODELO: None,
        webhook.CAMPO_POTENCIA: formato.potencia,
        webhook.CAMPO_TRACCION: formato.traccion,
        webhook.CAMPO_ANIO_COMERCIAL: formato.anio,
    }
    ejemplos = {"potencia": "380 CV", "traccion": "4x2", "anio": "2024"}
    for campo, convertir in convertidores.items():
        p = por_campo.get(campo)
        if p is None:
            continue
        if p["tipo"] not in TIPOS_CON_OPCIONES:
            errores.append(f"campo '{campo}': debe ser de seleccion_unica o seleccion_multiple.")
        elif convertir:
            malas = [o for o in p.get("opciones") or [] if convertir(o) is None]
            if malas:
                errores.append(f"campo '{campo}': opciones con formato inválido {malas} (ej.: {ejemplos[campo]}).")


def validar_definicion(datos):
    errores = []
    if not isinstance(datos, dict):
        return None, ["El cuerpo debe ser un objeto JSON."]

    limpia = {}
    titulo = _texto(datos.get("titulo"), 200)
    if titulo is None:
        errores.append("titulo: obligatorio (máx. 200 caracteres).")
    limpia["titulo"] = titulo

    aprobacion = _entero(datos.get("puntajeAprobacion"), 0, 10000)
    if aprobacion is None:
        errores.append("puntajeAprobacion: entero mayor o igual a 0.")
    limpia["puntajeAprobacion"] = aprobacion

    instrucciones = datos.get("instrucciones", [])
    if not (isinstance(instrucciones, list) and len(instrucciones) <= 10
            and all(_texto(i, 1500) for i in instrucciones)):
        errores.append("instrucciones: lista de hasta 10 textos (admite <strong>).")
        instrucciones = []
    limpia["instrucciones"] = [i.strip() for i in instrucciones]

    aviso = datos.get("avisoPrivacidad", "")
    if _texto(aviso, 1000, obligatorio=False) is None:
        errores.append("avisoPrivacidad: texto de hasta 1000 caracteres.")
        aviso = ""
    limpia["avisoPrivacidad"] = aviso.strip()

    secciones = datos.get("secciones")
    if not isinstance(secciones, list) or not 1 <= len(secciones) <= MAX_SECCIONES:
        errores.append(f"secciones: lista de 1 a {MAX_SECCIONES} secciones.")
        return None, errores

    limpias, total_preguntas, puntaje_total, campos = [], 0, 0, set()
    for i, seccion in enumerate(secciones):
        ruta = f"secciones[{i}]"
        if not isinstance(seccion, dict) or not isinstance(seccion.get("preguntas"), list) or not seccion["preguntas"]:
            errores.append(f"{ruta}: debe tener titulo y una lista de preguntas no vacía.")
            continue
        titulo_seccion = _texto(seccion.get("titulo"), 300)
        if titulo_seccion is None:
            errores.append(f"{ruta}.titulo: obligatorio (máx. 300 caracteres).")

        preguntas = []
        for j, pregunta in enumerate(seccion["preguntas"]):
            total_preguntas += 1
            valida = _validar_pregunta(pregunta, f"{ruta}.preguntas[{j}]", i == 0, errores)
            if valida is None:
                continue
            campo = valida.get("campo")
            if campo is not None:
                if campo in campos:
                    errores.append(f"{ruta}.preguntas[{j}].campo: '{campo}' está repetido.")
                campos.add(campo)
            puntaje_total += valida.get("puntos", 0)
            preguntas.append(valida)
        limpias.append({"titulo": titulo_seccion, "preguntas": preguntas})

    if limpias and limpias[0]["preguntas"]:
        _validar_campos_registro(limpias[0], errores)

    if total_preguntas > MAX_PREGUNTAS:
        errores.append(f"El formulario supera {MAX_PREGUNTAS} preguntas.")
    if aprobacion is not None and aprobacion > puntaje_total:
        errores.append(f"puntajeAprobacion ({aprobacion}) no puede superar el puntaje total ({puntaje_total}).")

    limpia["secciones"] = limpias
    return (None, errores) if errores else (limpia, [])
