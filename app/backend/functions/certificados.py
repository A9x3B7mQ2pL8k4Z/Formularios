"""Certificados HTML a PDF, en memoria, para respuestas de exactamente 100 puntos."""
import base64
import threading
from datetime import datetime

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from .config import CARPETA_FRONTEND
from .formato import MESES

_BLOQUEO_PDF = threading.Lock()


def renderizar_html(payload, titulo, id_certificado):
    """Escapa los datos del participante antes de insertarlos en la plantilla."""
    entorno = Environment(
        loader=FileSystemLoader(str(CARPETA_FRONTEND / "templates")),
        autoescape=select_autoescape(["html"]),
        undefined=StrictUndefined,
    )
    fecha = datetime.strptime(payload["registro"]["fecha_atencion"], "%d-%m-%Y")
    fecha_larga = f"{fecha.day:02d} de {MESES[fecha.month - 1].lower()} de {fecha.year}"
    return entorno.get_template("certificado.html").render(
        respuesta=payload["respuesta"], registro=payload["registro"],
        id_certificado=id_certificado,
        titulo=titulo, fecha_larga=fecha_larga,
    )


def generar_pdf(html):
    """Convierte el HTML a A4 sin navegador, red ni archivos temporales."""
    import pymupdf

    # El motor PDF no admite llamadas simultáneas desde hilos del mismo proceso.
    with _BLOQUEO_PDF:
        story = pymupdf.Story(html=html)
        pagina = pymupdf.paper_rect("a4")
        contenido = pagina + (40, 32, -40, -40)

        def rectangulo(numero, _ocupado):
            # Evita que una plantilla mal formada genere páginas sin límite.
            if numero >= 5:
                raise ValueError("El certificado excede el máximo de páginas permitido.")
            return pagina, contenido, None

        with story.write_with_links(rectangulo) as documento:
            documento.set_metadata({"title": "Certificado Academia Volvo", "author": "Academia Volvo"})
            documento.subset_fonts()
            return documento.tobytes(garbage=4, deflate=True)


def crear_adjunto(payload, titulo, id_certificado=None):
    """Objeto JSON para Make o None si no corresponde emitir certificado."""
    if payload["puntuacion"] != 100:
        return None
    if type(id_certificado) is not int or id_certificado < 1:
        raise ValueError("Falta un ID numérico válido para el certificado.")
    pdf = generar_pdf(renderizar_html(payload, titulo, id_certificado))
    nombre = "_".join(payload["registro"]["nombre_conductor"].title().split())
    return {
        "nombre_archivo": f"Certificado_{nombre}.pdf",
        "codificacion": "base64",
        "contenido_base64": base64.b64encode(pdf).decode("ascii"),
    }
