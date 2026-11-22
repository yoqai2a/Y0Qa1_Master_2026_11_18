"""Configuración de logging común para los programas de línea de comandos.

El nivel se elige con la variable de entorno ``Y0QA1_LOG`` (DEBUG, INFO, WARNING, ERROR).
Por defecto es INFO. Los mensajes INFO y DEBUG van a stdout; WARNING y superiores, a stderr.
"""
from __future__ import annotations

import logging
import os
import sys

_FORMATO = "%(message)s"
_configurado = False


class _SoloHasta(logging.Filter):
    def __init__(self, maximo: int) -> None:
        super().__init__()
        self.maximo = maximo

    def filter(self, registro: logging.LogRecord) -> bool:
        return registro.levelno <= self.maximo


def configurar(nivel: str | int | None = None) -> None:
    """Deja el logging listo (se puede llamar varias veces; solo actúa la primera)."""
    global _configurado
    if _configurado:
        return
    _configurado = True
    if nivel is None:
        nivel = os.environ.get("Y0QA1_LOG", "INFO").upper()
    raiz = logging.getLogger()
    raiz.setLevel(nivel)
    salida = logging.StreamHandler(sys.stdout)
    salida.addFilter(_SoloHasta(logging.INFO))
    errores = logging.StreamHandler(sys.stderr)
    errores.setLevel(logging.WARNING)
    for manejador in (salida, errores):
        manejador.setFormatter(logging.Formatter(_FORMATO))
        raiz.addHandler(manejador)
    # requests/urllib3 son muy verbosos en DEBUG; no los mezclamos con nuestros mensajes.
    logging.getLogger("urllib3").setLevel(logging.WARNING)
