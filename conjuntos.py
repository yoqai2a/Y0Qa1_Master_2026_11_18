"""Traduce un conjunto de variables/niveles del TOML a la consulta del filtro NOMADS."""
from __future__ import annotations

from urllib.parse import quote

from .configuracion import Conjunto


def _codificar(nombre: str) -> str:
    # NOMADS espera '=', '^' y '/' codificados (PV%3D-2e-06_(Km%5E2%2Fkg%2Fs)_surface)
    # pero los paréntesis tal cual.
    return quote(nombre, safe="()")


def construir_seleccion(conjunto: Conjunto, parametros_extra: tuple[str, ...] = ()) -> str:
    """Devuelve los parámetros `var_*`/`lev_*` unidos con '&' (sin '&' inicial).

    Elimina duplicados conservando el orden: la consulta es más corta y NOMADS
    no distingue repeticiones.
    """
    partes: list[str] = []
    if conjunto.todas_variables:
        partes.append("all_var=on")
    if conjunto.todos_niveles:
        partes.append("all_lev=on")
    partes += [f"var_{_codificar(v)}=on" for v in conjunto.variables]
    partes += [f"lev_{_codificar(n)}=on" for n in conjunto.niveles]
    partes += [f"{_codificar(p)}=on" for p in parametros_extra]
    return "&".join(dict.fromkeys(partes))
