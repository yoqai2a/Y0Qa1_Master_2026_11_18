"""Integración con GitHub Actions (no hace nada fuera de Actions)."""
from __future__ import annotations

import os
from pathlib import Path


def en_ci() -> bool:
    return os.environ.get("GITHUB_ACTIONS") == "true" or os.environ.get("CI") == "true"


def exportar_salidas(**valores: str) -> None:
    """Escribe en $GITHUB_OUTPUT para que los pasos siguientes usen fecha/ciclo."""
    ruta = os.environ.get("GITHUB_OUTPUT")
    if ruta:
        with Path(ruta).open("a", encoding="utf-8") as f:
            for clave, valor in valores.items():
                f.write(f"{clave}={valor}\n")


def escribir_resumen(markdown: str) -> None:
    ruta = os.environ.get("GITHUB_STEP_SUMMARY")
    if ruta:
        with Path(ruta).open("a", encoding="utf-8") as f:
            f.write(markdown + "\n")


def anotar(nivel: str, mensaje: str) -> None:
    """Anotación visible en la pestaña del run (nivel: notice, warning o error)."""
    if en_ci():
        print(f"::{nivel}::{mensaje}", flush=True)
