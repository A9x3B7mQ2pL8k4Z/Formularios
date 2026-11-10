"""Lectura y verificación del token de acceso (cookie HttpOnly por formulario)."""
import re

from flask import current_app, request

from ..functions import tokens

PATRON_ID_FORMULARIO = re.compile(r"^[a-z0-9_-]{1,64}$")


def nombre_cookie(id_formulario):
    return f"acceso_{id_formulario}"


def config():
    return current_app.extensions["config"]


def repositorio():
    return current_app.extensions["repositorio"]


def id_formulario_valido(id_formulario):
    return bool(PATRON_ID_FORMULARIO.match(id_formulario or ""))


def token_de_la_peticion(id_formulario):
    cabecera = request.headers.get("Authorization", "")
    if cabecera.startswith("Bearer "):
        return cabecera[7:].strip()
    return request.cookies.get(nombre_cookie(id_formulario), "")


def acceso_valido(id_formulario):
    """True si la petición trae un token vigente y emitido para ESTE formulario."""
    if not id_formulario_valido(id_formulario):
        return False
    token = token_de_la_peticion(id_formulario)
    if not token:
        return False
    cfg = config()
    try:
        tokens.validar(cfg.SECRET_KEY, token, id_formulario, cfg.TOKEN_TTL_SEGUNDOS)
        return True
    except tokens.TokenInvalido:
        return False


def poner_cookie_de_acceso(respuesta, id_formulario, token):
    cfg = config()
    respuesta.set_cookie(
        nombre_cookie(id_formulario),
        token,
        max_age=cfg.TOKEN_TTL_SEGUNDOS,
        httponly=True,
        secure=cfg.EN_PRODUCCION,
        samesite="Lax",
        path="/",
    )
    return respuesta
