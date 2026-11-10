"""Huellas SHA-256 de certificados por seis campos, compartidas entre formularios.

Vencen siete días después de que Make confirma recepción. Redis no guarda los
datos personales ni el PDF. Sin Redis, solo en desarrollo, se usa memoria local.
"""
import hashlib
import json
import secrets
import threading
import time

from . import formato

PREFIJO = "duplicados:certificados:v1:"
TTL_SEGUNDOS = 7 * 24 * 60 * 60
RESERVA_SEGUNDOS = 120

# Comprobar propietario y actualizar/borrar en una sola operación.
CAMBIAR_ESTADO = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then return 0 end
if ARGV[2] == 'liberar' then
    return redis.call('DEL', KEYS[1])
end
redis.call('SET', KEYS[1], 'enviado', 'EX', ARGV[2])
return 1
"""


def crear_huella(formulario, respuestas):
    valores = {
        pregunta.get('campo'): respuestas.get(pregunta['id'])
        for pregunta in formulario['secciones'][0]['preguntas']
    }
    campos = ('rut_empresa', 'rut', 'modelo', 'traccion', 'anio', 'potencia')
    if any(valores.get(campo) in (None, '', []) for campo in campos):
        raise ValueError('Faltan campos requeridos para identificar el certificado.')

    def rut(valor):
        return ''.join(c for c in formato.texto_mayusculas(valor) if c not in '.- ')

    def seleccion(valor, convertir):
        lista = valor if isinstance(valor, list) else [valor]
        return sorted(set(convertir(elemento) for elemento in lista))

    def canonico(valor, convertir):
        resultado = convertir(valor)
        if resultado is None:
            raise ValueError('Selección inválida para identificar el certificado.')
        return resultado[0]

    identidad = [
        rut(valores['rut_empresa']), rut(valores['rut']),
        seleccion(valores['modelo'], formato.texto_mayusculas),
        seleccion(valores['traccion'], lambda v: canonico(v, formato.traccion)),
        seleccion(valores['anio'], lambda v: canonico(v, formato.anio)),
        seleccion(valores['potencia'], lambda v: canonico(v, formato.potencia)),
    ]
    contenido = json.dumps(identidad, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(contenido.encode('utf-8')).hexdigest()


class RegistroHuellas:
    def __init__(self, cliente=None, reloj=time.monotonic):
        self.cliente = cliente
        self._reloj = reloj
        self._memoria = {}
        self._bloqueo = threading.Lock()

    def reservar(self, huella):
        """Devuelve (estado, propietario). Estado: nuevo, enviado o pendiente."""
        clave = PREFIJO + huella
        propietario = secrets.token_hex(16)
        valor = 'pendiente:' + propietario
        if self.cliente is not None:
            # Reintentar si la clave venció justo entre SET y GET.
            for _ in range(3):
                if self.cliente.comando('SET', clave, valor, 'NX', 'EX', RESERVA_SEGUNDOS):
                    return 'nuevo', propietario
                actual = self.cliente.comando('GET', clave)
                if actual is not None:
                    return ('enviado' if actual == 'enviado' else 'pendiente'), None
            return 'pendiente', None
        with self._bloqueo:
            ahora = self._reloj()
            self._memoria = {k: v for k, v in self._memoria.items() if v[1] > ahora}
            if clave in self._memoria:
                actual = self._memoria[clave][0]
                return ('enviado' if actual == 'enviado' else 'pendiente'), None
            self._memoria[clave] = (valor, ahora + RESERVA_SEGUNDOS)
            return 'nuevo', propietario

    def _cambiar(self, huella, propietario, accion):
        clave = PREFIJO + huella
        esperado = 'pendiente:' + propietario
        if self.cliente is not None:
            return bool(self.cliente.comando('EVAL', CAMBIAR_ESTADO, 1, clave, esperado, accion))
        with self._bloqueo:
            actual, vence = self._memoria.get(clave, (None, 0))
            if actual != esperado or vence <= self._reloj():
                return False
            if accion == 'liberar':
                del self._memoria[clave]
            else:
                self._memoria[clave] = ('enviado', self._reloj() + TTL_SEGUNDOS)
            return True

    def confirmar(self, huella, propietario):
        if not self._cambiar(huella, propietario, TTL_SEGUNDOS):
            raise RuntimeError('Venció la reserva del certificado antes de confirmar el envío.')

    def liberar(self, huella, propietario):
        self._cambiar(huella, propietario, 'liberar')
