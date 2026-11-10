"""
Reglas de formato de los datos que viajan a Make (funciones puras, sin red ni base de datos).

  - Nombres (razón social, conductor, instructor): MAYÚSCULAS, sin espacios sobrantes, con tildes.
  - RUT: letra K en mayúscula.
  - Modelo / Potencia / Tracción / Año comercial: separados por " - " (sin guion si es uno solo).
  - Fecha de atención: America/Santiago, dd-MM-yyyy. Mes en español. Año como número.
"""
import re
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo

ZONA_HORARIA = ZoneInfo("America/Santiago")
SEPARADOR = " - "

MESES = (
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
)  # tabla fija: el locale del servidor no es confiable en Vercel

_PATRON_POTENCIA = re.compile(r"^(\d{2,4})\s*(?:CV)?$", re.IGNORECASE)
_PATRON_TRACCION = re.compile(r"^(\d{1,2})\s*x\s*(\d{1,2})$", re.IGNORECASE)
_PATRON_ANIO = re.compile(r"^\d{4}$")


# ---------------------------------------------------------------- textos y RUT
def texto_mayusculas(valor):
    """'  josé   núñez ' -> 'JOSÉ NÚÑEZ'. NFC para no romper tildes escritas como carácter combinado."""
    return " ".join(unicodedata.normalize("NFC", str(valor)).split()).upper()


def rut(valor):
    """Sin espacios y con la K en mayúscula (el formato 12345678-K lo valida el evaluador)."""
    return "".join(str(valor).split()).upper()


# ------------------------------------------------- opciones (un valor por opción)
def potencia(valor):
    """'380 CV' / '380cv' / '380' -> ('380CV', 380). None si no calza."""
    m = _PATRON_POTENCIA.match(str(valor).strip())
    return (f"{int(m.group(1))}CV", int(m.group(1))) if m else None


def traccion(valor):
    """'4X2' -> ('4x2', (4, 2)). La x queda en minúscula. None si no calza."""
    m = _PATRON_TRACCION.match(str(valor).strip())
    if not m:
        return None
    a, b = int(m.group(1)), int(m.group(2))
    return f"{a}x{b}", (a, b)


def anio(valor):
    texto = str(valor).strip()
    return (texto, int(texto)) if _PATRON_ANIO.match(texto) else None


def _como_lista(seleccion):
    if seleccion is None:
        return []
    return [seleccion] if isinstance(seleccion, str) else list(seleccion)


def _unir(textos):
    return SEPARADOR.join(dict.fromkeys(textos))  # sin repetidos; con uno solo no hay separador


def unir_modelos(seleccion, opciones):
    """MAYÚSCULAS, en el orden en que las opciones aparecen en el formulario."""
    seleccion = _como_lista(seleccion)
    orden = {o: i for i, o in enumerate(opciones)}
    seleccion.sort(key=lambda v: orden.get(v, len(orden)))
    return _unir(texto_mayusculas(v) for v in seleccion)


def _unir_ordenados(seleccion, convertir, nombre):
    pares = []
    for valor in _como_lista(seleccion):
        convertido = convertir(valor)
        if convertido is None:
            raise ValueError(f"Valor de {nombre} con formato inesperado: {valor!r}")
        pares.append(convertido)
    pares.sort(key=lambda par: par[1])  # menor a mayor
    return _unir(texto for texto, _ in pares)


def unir_potencias(seleccion):
    return _unir_ordenados(seleccion, potencia, "potencia")


def unir_tracciones(seleccion):
    return _unir_ordenados(seleccion, traccion, "tracción")


def unir_anios(seleccion):
    return _unir_ordenados(seleccion, anio, "año comercial")


# ---------------------------------------------------------------------- fecha
def ahora_santiago():
    return datetime.now(ZONA_HORARIA)


def fecha_atencion(momento):
    return momento.strftime("%d-%m-%Y")


def mes(momento):
    return MESES[momento.month - 1]
