"""Utilidades de tiempo y formato para los mensajes de consola."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

log = logging.getLogger(__name__)


def duracion(segundos: float) -> str:
    """Formatea una duración como HH:MM:SS.ss (sin limitar las horas)."""
    centesimas = round(max(0.0, segundos) * 100)
    horas, resto = divmod(centesimas, 360_000)
    minutos, resto = divmod(resto, 6_000)
    enteros, fraccion = divmod(resto, 100)
    return f"{horas:02d}:{minutos:02d}:{enteros:02d}.{fraccion:02d}"


def ahora_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def imprimir_marca(etapa: str, inicio_etapa: float, inicio_programa: float) -> None:
    ahora = time.perf_counter()
    log.info(f"{etapa}: {ahora_utc()} | duración: {duracion(ahora - inicio_etapa)}"
          f" | desde el inicio: {duracion(ahora - inicio_programa)}")


def tamano_legible(n: float) -> str:
    for unidad in ("B", "KB", "MB", "GB"):
        if n < 1024 or unidad == "GB":
            return f"{n:.1f} {unidad}" if unidad != "B" else f"{int(n)} B"
        n /= 1024
