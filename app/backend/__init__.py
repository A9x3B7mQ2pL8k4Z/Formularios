from flask import Flask, g, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

from .functions import errores
from .functions.config import CARPETA_FRONTEND, Config
from .functions.repositorio import ErrorAlmacenamiento, crear_repositorio


def crear_app(config=Config):
    config.validar()

    app = Flask(
        __name__,
        template_folder=str(CARPETA_FRONTEND / "templates"),
        static_folder=str(CARPETA_FRONTEND / "static"),
        static_url_path="/static",
    )
    app.config.from_object(config)
    app.extensions["config"] = config
    app.extensions["repositorio"] = crear_repositorio(config)

    from .routes.admin import admin_bp
    from .routes.api import api_bp
    from .routes.paginas import paginas_bp

    app.register_blueprint(paginas_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(admin_bp)

    @app.before_request
    def limitar_envios_publicos():
        # El tope general (MAX_CONTENT_LENGTH) es mayor por las imágenes del admin;
        # fuera de /admin sigue valiendo el límite chico de siempre.
        if not request.path.startswith("/admin") and (request.content_length or 0) > config.MAX_ENVIO_BYTES:
            return jsonify({"error": "Solicitud demasiado grande."}), 413

    def registrar_error_programa(error):
        """Notifica fallos del servidor en cualquier ruta, con los datos disponibles."""
        errores.registrar_error(
            app.extensions["config"], app.extensions["repositorio"],
            errores.descripcion_de(error), contexto=getattr(g, "envio", None),
        )

    @app.errorhandler(ErrorAlmacenamiento)
    def almacenamiento_caido(error):
        app.logger.error("Error de almacenamiento: %s", error)
        registrar_error_programa(error)
        if request.path.startswith(("/api", "/admin")):
            return jsonify({"error": "Servicio no disponible. Inténtalo nuevamente."}), 503
        return render_template("index.html"), 503

    @app.errorhandler(Exception)
    def error_inesperado(error):
        if isinstance(error, HTTPException):  # 404, 405, 413...: no son fallos del servidor
            return error
        app.logger.exception("Error no controlado")
        registrar_error_programa(error)
        if request.path.startswith(("/api", "/admin")):
            return jsonify({"error": "Error interno. Inténtalo nuevamente."}), 500
        return "Error interno.", 500

    @app.after_request
    def cabeceras_de_seguridad(respuesta):
        respuesta.headers.setdefault("X-Content-Type-Options", "nosniff")
        respuesta.headers.setdefault("Referrer-Policy", "same-origin")
        if respuesta.mimetype in ("text/html", "application/json"):
            respuesta.headers["Cache-Control"] = "no-store"
        return respuesta

    return app
