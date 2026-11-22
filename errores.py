"""Mensajes de error para el usuario: simples en pantalla, con el detalle técnico en el registro.

Los detalles internos (rutas, respuestas de GitHub, configuración de tokens) no deben verse en la
interfaz de cualquier usuario. Quien administra el visor puede verlos en pantalla definiendo
``MOSTRAR_DETALLES_ERROR = "true"`` en los secretos o en el entorno; si no, quedan en el registro.
"""
from __future__ import annotations

import logging
import os

import streamlit as st

log = logging.getLogger("visor")


def detalles_visibles() -> bool:
    try:
        valor = st.secrets.get("MOSTRAR_DETALLES_ERROR")
    except Exception:
        valor = None
    if valor in (None, ""):
        valor = os.environ.get("MOSTRAR_DETALLES_ERROR", "")
    return str(valor).strip().casefold() in {"1", "true", "si", "sí", "yes"}


def mostrar_error(mensaje: str, exc: BaseException | None = None, *, aviso: bool = False) -> None:
    """Muestra ``mensaje`` al usuario y registra la excepción completa."""
    if exc is not None:
        log.error("%s | %s: %s", mensaje, type(exc).__name__, exc, exc_info=exc)
    texto = mensaje
    if exc is not None and detalles_visibles():
        texto += f"\n\nDetalle técnico: {exc}"
    (st.warning if aviso else st.error)(texto)
