"""
Páginas HTML.

  /?f=<id_formulario>   URL que lleva el QR. Al escanear se EMITE un token firmado
                        (5 días), se guarda en una cookie HttpOnly y se redirige
                        al formulario correspondiente.
  /?token=<token>       Ingreso con un token ya emitido (p. ej. generado por el admin
                        en el futuro). Se valida y redirige igual.
  /formulario/<id>      Solo se muestra con un token vigente para ESE formulario.
  Cualquier otro caso   Vista "Acceso inválido" del index.
"""
from flask import Blueprint, redirect, render_template, request, url_for

from ..functions import tokens
from . import acceso

paginas_bp = Blueprint("paginas", __name__)


def _pagina_de_error(codigo=403):
    return render_template("index.html"), codigo


def _ir_al_formulario(id_formulario, token):
    respuesta = redirect(url_for("paginas.formulario", id_formulario=id_formulario))
    return acceso.poner_cookie_de_acceso(respuesta, id_formulario, token)


@paginas_bp.get("/")
def index():
    cfg = acceso.config()

    token = request.args.get("token")
    if token:
        try:
            id_formulario = tokens.leer_formulario_sin_validar_expiracion(cfg.SECRET_KEY, token)
            tokens.validar(cfg.SECRET_KEY, token, id_formulario, cfg.TOKEN_TTL_SEGUNDOS)
        except tokens.TokenInvalido:
            return _pagina_de_error()
        if not acceso.id_formulario_valido(id_formulario) or acceso.repositorio().obtener(id_formulario) is None:
            return _pagina_de_error()
        return _ir_al_formulario(id_formulario, token)

    id_formulario = request.args.get("f")
    if id_formulario:
        if not acceso.id_formulario_valido(id_formulario) or acceso.repositorio().obtener(id_formulario) is None:
            return _pagina_de_error(404)
        return _ir_al_formulario(id_formulario, tokens.emitir(cfg.SECRET_KEY, id_formulario))

    return render_template("index.html")


@paginas_bp.get("/formulario/<id_formulario>")
def formulario(id_formulario):
    if not acceso.acceso_valido(id_formulario):
        return _pagina_de_error()
    if acceso.repositorio().obtener(id_formulario) is None:
        return _pagina_de_error(404)
    return render_template(
        "formularios.html", id_formulario=id_formulario,
        fondo_formularios_url=acceso.repositorio().obtener_fondo(),
    )
