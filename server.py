"""
Punto de entrada.
  Local:   python server.py
  Vercel:  expone la variable `app` (Flask).
"""
from app.backend import crear_app

app = crear_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=not app.extensions["config"].EN_PRODUCCION)
