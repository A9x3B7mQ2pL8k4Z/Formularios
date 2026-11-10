"""
Acceso a los formularios.

El resto del backend SOLO usa `obtener` / `listar` (lectura) y, desde la API de
administración, `crear` / `guardar` / `eliminar`.

Dónde viven los datos:
  - Producción (Vercel): Upstash Redis. Cada formulario es un JSON en la clave
    `formulario:<codigo>`; el set `formularios` lista los códigos y el contador
    `formularios:contador` entrega el número de prueba (1, 2, 3...).
  - Local sin Redis configurado: `data/formularios.json` (solo lectura, para probar).

`codigo` = identificador del formulario en la URL / QR: 10 caracteres alfanuméricos aleatorios
(los formularios creados antes conservan su UUID).
`numero` = número de prueba (1, 2, 3...), se asigna solo al crear.

Los IDs de pregunta NO se guardan: se generan al leer, en el orden en que están las
preguntas (todas, de corrido a través de las secciones): `P<numero>-<n>`, p. ej. `P1-1`.
Si el admin reordena o borra preguntas, los IDs se recalculan solos.

`correcta` NUNCA sale del backend: usa `formulario_publico()`.
"""
import copy
import json
import re
import secrets
import threading
from pathlib import Path

import requests

from .duplicados import RegistroHuellas

MAX_ERRORES = 1000  # errores recientes que se conservan en Redis

PATRON_CODIGO = re.compile(r"^[a-z0-9_-]{1,64}$")

# Código corto de la URL/QR. Sin 0/o/1/l/i para que se pueda leer y teclear sin confundirse:
# 31^10 combinaciones (~49 bits) con generador criptográfico: imposible de adivinar a ciegas.
ALFABETO_CODIGO = "abcdefghjkmnpqrstuvwxyz23456789"
LARGO_CODIGO = 10


def generar_codigo():
    return "".join(secrets.choice(ALFABETO_CODIGO) for _ in range(LARGO_CODIGO))


class ErrorAlmacenamiento(Exception):
    """La base de datos no respondió o devolvió un error."""


class FormularioExistente(Exception):
    """Ya existe un formulario con ese código."""


def codigo_valido(codigo):
    return bool(PATRON_CODIGO.match(codigo or ""))


def preparar_formulario(codigo, definicion):
    """Copia del formulario guardado + `id`, `numero`, IDs de pregunta y `puntajeTotal`."""
    formulario = copy.deepcopy(definicion)
    formulario["id"] = codigo
    numero_prueba = formulario.get("numero", 0)

    contador, total = 0, 0
    for seccion in formulario["secciones"]:
        for pregunta in seccion["preguntas"]:
            contador += 1
            pregunta["id"] = f"P{numero_prueba}-{contador}"
            pregunta["numero"] = contador
            total += pregunta.get("puntos", 0)
    formulario["puntajeTotal"] = total
    return formulario


class RepositorioFormularios:
    def obtener_fondo(self):
        raise NotImplementedError

    def guardar_fondo(self, src):
        raise NotImplementedError

    def inicializar_fondo(self, src=""):
        raise NotImplementedError

    def obtener(self, codigo):
        raise NotImplementedError

    def listar(self):
        raise NotImplementedError

    def crear(self, definicion, codigo=None):
        raise NotImplementedError

    def guardar(self, codigo, definicion):
        raise NotImplementedError

    def eliminar(self, codigo):
        raise NotImplementedError

    def siguiente_numero_respuesta(self, numero_formulario):
        """Contador atómico por formulario: 1, 2, 3... (el ID de respuesta es P<numero>-<n>)."""
        raise NotImplementedError

    def inicializar_contador_certificados(self):
        raise NotImplementedError

    def siguiente_numero_certificado(self):
        """Numeración global para certificados: 1, 2, 3... Solo se usa con 100 puntos."""
        raise NotImplementedError

    # --- registro de errores de envío (ver errores.py) ---
    def guardar_error(self, entrada):
        raise NotImplementedError

    def listar_errores(self, limite=100):
        raise NotImplementedError



class RepositorioJson(RepositorioFormularios):
    """Solo lectura. Úsalo únicamente en local, sin Redis."""

    def __init__(self, ruta):
        self.huellas = RegistroHuellas()
        self._ruta = Path(ruta)
        self._respuestas = {}  # contador en memoria: SOLO para pruebas locales
        self._certificados = 0  # ídem; en producción se usa Redis
        self._errores = []  # registro local en memoria
        self._bloqueo = threading.Lock()

    def _cargar(self):
        with self._ruta.open(encoding="utf-8") as archivo:
            return json.load(archivo)

    def obtener(self, codigo):
        definicion = self._cargar().get(codigo)
        return None if definicion is None else preparar_formulario(codigo, definicion)

    def listar(self):
        return list(self._cargar().keys())

    def _solo_lectura(self, *_, **__):
        raise ErrorAlmacenamiento("Sin Redis configurado los formularios son de solo lectura.")

    crear = guardar = eliminar = _solo_lectura
    guardar_fondo = inicializar_fondo = _solo_lectura

    def obtener_fondo(self):
        return ""

    def guardar_error(self, entrada):
        with self._bloqueo:
            self._errores.insert(0, entrada)
            del self._errores[MAX_ERRORES:]

    def listar_errores(self, limite=100):
        return list(self._errores[:limite])

    def siguiente_numero_respuesta(self, numero_formulario):
        with self._bloqueo:
            self._respuestas[numero_formulario] = self._respuestas.get(numero_formulario, 0) + 1
            return self._respuestas[numero_formulario]

    def inicializar_contador_certificados(self):
        pass  # Ya empieza en cero al construir el repositorio local.

    def siguiente_numero_certificado(self):
        with self._bloqueo:
            self._certificados += 1
            return self._certificados


class ClienteUpstash:
    """Cliente mínimo de la API REST de Upstash (usa `requests`, sin dependencias nuevas)."""

    def __init__(self, url, token, timeout=5):
        self._url = url.rstrip("/")
        self._cabeceras = {"Authorization": f"Bearer {token}"}
        self._timeout = timeout

    def _enviar(self, ruta, cuerpo):
        try:
            respuesta = requests.post(
                self._url + ruta, json=cuerpo, headers=self._cabeceras, timeout=self._timeout
            )
            datos = respuesta.json()
        except (requests.RequestException, ValueError) as error:
            raise ErrorAlmacenamiento("No hay conexión con la base de datos.") from error
        if not respuesta.ok:
            raise ErrorAlmacenamiento(f"Error de la base de datos: {datos}")
        return datos

    def comando(self, *argumentos):
        datos = self._enviar("", list(argumentos))
        if isinstance(datos, dict) and datos.get("error"):
            raise ErrorAlmacenamiento(datos["error"])
        return datos["result"]

    def pipeline(self, comandos):
        resultados = self._enviar("/pipeline", [list(c) for c in comandos])
        for resultado in resultados:
            if resultado.get("error"):
                raise ErrorAlmacenamiento(resultado["error"])
        return [resultado["result"] for resultado in resultados]


class RepositorioRedis(RepositorioFormularios):
    CLAVE_FONDO = "configuracion:fondo_formularios"

    def obtener_fondo(self):
        return self._redis.comando("GET", self.CLAVE_FONDO) or ""

    def guardar_fondo(self, src):
        self._redis.comando("SET", self.CLAVE_FONDO, src)

    def inicializar_fondo(self, src=""):
        """Crea la configuración solo si no existe; conserva un fondo ya elegido."""
        return self._redis.comando("SET", self.CLAVE_FONDO, src, "NX")

    CLAVE_INDICE = "formularios"
    CLAVE_CONTADOR = "formularios:contador"
    CLAVE_CERTIFICADOS = "certificados:contador"  # global, independiente de formularios y respuestas
    CLAVE_RESPUESTAS = "respuestas:contador:{}"  # un contador por formulario
    CLAVE_ERRORES = "errores:log"  # lista, el más reciente primero

    def __init__(self, cliente):
        self._redis = cliente
        self.huellas = RegistroHuellas(cliente)

    @staticmethod
    def _clave(codigo):
        return f"formulario:{codigo}"

    def _leer(self, codigo):
        if not codigo_valido(codigo):
            return None
        crudo = self._redis.comando("GET", self._clave(codigo))
        return json.loads(crudo) if crudo else None

    @staticmethod
    def _serializar(documento):
        return json.dumps(documento, ensure_ascii=False, separators=(",", ":"))

    def obtener(self, codigo):
        documento = self._leer(codigo)
        return None if documento is None else preparar_formulario(codigo, documento)

    def listar(self):
        return sorted(self._redis.comando("SMEMBERS", self.CLAVE_INDICE))

    def crear(self, definicion, codigo=None):
        """Guarda un formulario nuevo. Devuelve (codigo, numero)."""
        if codigo is None:
            for _ in range(5):  # una colisión es prácticamente imposible, pero se verifica
                codigo = generar_codigo()
                if not self._redis.comando("EXISTS", self._clave(codigo)):
                    break
            else:
                raise ErrorAlmacenamiento("No se pudo generar un código único.")
        if not codigo_valido(codigo):
            raise ValueError("Código de formulario inválido.")
        if self._redis.comando("EXISTS", self._clave(codigo)):
            raise FormularioExistente(codigo)

        numero = int(self._redis.comando("INCR", self.CLAVE_CONTADOR))
        documento = {"numero": numero, **definicion}
        self._redis.pipeline([
            ("SET", self._clave(codigo), self._serializar(documento)),
            ("SADD", self.CLAVE_INDICE, codigo),
        ])
        return codigo, numero

    def guardar(self, codigo, definicion):
        """Reemplaza un formulario existente (conserva su número). False si no existe."""
        actual = self._leer(codigo)
        if actual is None:
            return False
        documento = {"numero": actual["numero"], **definicion}
        self._redis.comando("SET", self._clave(codigo), self._serializar(documento))
        return True

    def siguiente_numero_respuesta(self, numero_formulario):
        """INCR es atómico en Redis: dos envíos simultáneos nunca reciben el mismo número.
        La clave se crea sola en el primer envío (INCR sobre una clave inexistente devuelve 1)."""
        return int(self._redis.comando("INCR", self.CLAVE_RESPUESTAS.format(int(numero_formulario))))

    def inicializar_contador_certificados(self):
        """SET NX conserva el valor existente, incluso si hay envíos simultáneos."""
        self._redis.comando("SET", self.CLAVE_CERTIFICADOS, 0, "NX")

    def siguiente_numero_certificado(self):
        return int(self._redis.comando("INCR", self.CLAVE_CERTIFICADOS))

    def guardar_error(self, entrada):
        comandos = [
            ("LPUSH", self.CLAVE_ERRORES, self._serializar(entrada)),
            ("LTRIM", self.CLAVE_ERRORES, 0, MAX_ERRORES - 1),
        ]
        self._redis.pipeline(comandos)

    def listar_errores(self, limite=100):
        return [json.loads(e) for e in self._redis.comando("LRANGE", self.CLAVE_ERRORES, 0, limite - 1)]

    def eliminar(self, codigo):
        if self._leer(codigo) is None:
            return False
        self._redis.pipeline([
            ("DEL", self._clave(codigo)),
            ("SREM", self.CLAVE_INDICE, codigo),
        ])
        return True


def formulario_publico(formulario):
    """Copia del formulario SIN las respuestas correctas (esto es lo que ve el navegador)."""
    publico = copy.deepcopy(formulario)
    for seccion in publico["secciones"]:
        for pregunta in seccion["preguntas"]:
            pregunta.pop("correcta", None)
    return publico


def crear_repositorio(config):
    if config.REDIS_URL and config.REDIS_TOKEN:
        return RepositorioRedis(ClienteUpstash(config.REDIS_URL, config.REDIS_TOKEN))
    return RepositorioJson(Path(__file__).parent.parent / "data" / "formularios.json")
