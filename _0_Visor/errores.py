"""Mensajes de error para el usuario: simples en pantalla, con el detalle técnico en el registro.

Los detalles internos (rutas, respuestas de GitHub, configuración de tokens) no deben verse en la
interfaz de cualquier usuario. Se muestran en pantalla en dos casos:
  * cuando el visor se abre desde el mismo PC donde corre (localhost / 127.0.0.1), y
  * cuando se define ``MOSTRAR_DETALLES_ERROR = "true"`` en los secretos o en el entorno.
``MOSTRAR_DETALLES_ERROR = "false"`` los oculta siempre. En cualquier caso quedan en el registro.
"""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

import streamlit as st

log = logging.getLogger("visor")
ARCHIVO_LOG = Path(__file__).resolve().parent / "errores_visor.log"


def _registrar_en_archivo() -> None:
    """Deja los errores (con su traza completa) en errores_visor.log, para poder abrirlos y copiarlos."""
    if any(getattr(h, "_y0qa1", False) for h in log.handlers):
        return
    try:
        manejador = RotatingFileHandler(ARCHIVO_LOG, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    except OSError:
        return
    manejador.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    manejador._y0qa1 = True
    log.addHandler(manejador)


def _acceso_local() -> bool:
    """True si el navegador entró por localhost (quien lo abre así es quien administra el visor)."""
    try:
        host = str(st.context.headers.get("Host", "")).strip().casefold()
    except Exception:       # sin sesión de Streamlit o versión sin st.context
        return False
    nombre = host[1:host.find("]")] if host.startswith("[") else (
        host.rsplit(":", 1)[0] if host.count(":") == 1 else host)
    return nombre in {"localhost", "127.0.0.1", "::1"}


def detalles_visibles() -> bool:
    try:
        valor = st.secrets.get("MOSTRAR_DETALLES_ERROR")
    except Exception:
        valor = None
    if valor in (None, ""):
        valor = os.environ.get("MOSTRAR_DETALLES_ERROR", "")
    if str(valor).strip():
        return str(valor).strip().casefold() in {"1", "true", "si", "sí", "yes"}
    return _acceso_local()


def mostrar_error(mensaje: str, exc: BaseException | None = None, *, aviso: bool = False) -> None:
    """Muestra ``mensaje`` al usuario y registra la excepción completa."""
    if exc is not None:
        _registrar_en_archivo()
        log.error("%s | %s: %s", mensaje, type(exc).__name__, exc, exc_info=exc)
    texto = mensaje
    if exc is not None:
        texto += f"\n\nTipo de error: {type(exc).__name__}."
        if detalles_visibles():
            texto += f"\n\nDetalle técnico: {exc}"
        else:
            texto += f" El detalle completo queda en el archivo {ARCHIVO_LOG.parent.name}/{ARCHIVO_LOG.name}."
    (st.warning if aviso else st.error)(texto)
