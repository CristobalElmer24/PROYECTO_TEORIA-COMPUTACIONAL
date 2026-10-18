"""Punto de entrada para Vercel (función serverless con la app Flask)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402

app = create_app()


class _QuitarPrefijo:
    """Por si Vercel entrega la ruta como /api/index, la convierte en /."""

    def __init__(self, wsgi):
        self.wsgi = wsgi

    def __call__(self, environ, start_response):
        ruta = environ.get("PATH_INFO", "")
        if ruta == "/api/index" or ruta.startswith("/api/index/"):
            environ["PATH_INFO"] = ruta[len("/api/index"):] or "/"
        return self.wsgi(environ, start_response)


app.wsgi_app = _QuitarPrefijo(app.wsgi_app)
