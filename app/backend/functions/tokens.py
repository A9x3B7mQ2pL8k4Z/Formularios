"""
Tokens firmados (sin base de datos).

Un token contiene SOLO el id del formulario y la fecha de emisión; la firma
(HMAC con SECRET_KEY) impide modificarlo. Vence a los TOKEN_TTL_SEGUNDOS (5 días).
Un token de un formulario no sirve para ningún otro formulario.
"""
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

SALT = "acceso-formulario-v1"


class TokenInvalido(Exception):
    """Firma incorrecta, token manipulado o de otro formulario."""


class TokenExpirado(TokenInvalido):
    """La firma es correcta pero pasaron más de 5 días."""


def _serializador(secret_key):
    return URLSafeTimedSerializer(secret_key, salt=SALT)


def emitir(secret_key, id_formulario):
    return _serializador(secret_key).dumps({"f": id_formulario})


def validar(secret_key, token, id_formulario_esperado, ttl_segundos):
    """Devuelve el id del formulario si el token es válido para ese formulario."""
    try:
        datos = _serializador(secret_key).loads(token, max_age=ttl_segundos)
    except SignatureExpired as error:
        raise TokenExpirado() from error
    except BadSignature as error:
        raise TokenInvalido() from error

    if not isinstance(datos, dict) or datos.get("f") != id_formulario_esperado:
        raise TokenInvalido()
    return datos["f"]


def leer_formulario_sin_validar_expiracion(secret_key, token):
    """Solo para el ingreso por `/?token=...`: devuelve el id de formulario que el token declara."""
    try:
        datos = _serializador(secret_key).loads(token)  # valida firma, ignora expiración
    except BadSignature as error:
        raise TokenInvalido() from error
    if not isinstance(datos, dict) or not isinstance(datos.get("f"), str):
        raise TokenInvalido()
    return datos["f"]
