"""Reparto de las capas en archivos .nc según la agrupación elegida."""
from __future__ import annotations

from .variables import Capa, limpiar


def _slug(capa: Capa, agrupacion: str) -> str:
    if agrupacion == "unico":
        return "Todo"
    if agrupacion == "grupo":
        return limpiar(capa.grupo)
    if agrupacion == "variable":
        return limpiar(capa.short_name)
    return capa.nombre


def planificar(capas: list[Capa], agrupacion: str, prefijo: str, fecha: str, ciclo: str,
              mensajes: dict[str, int] | None = None) -> dict[str, list[Capa]]:
    """{nombre_de_archivo: [capas]}, en el orden del .toml.

    Los nombres de archivo se vuelven únicos sin distinguir mayúsculas: en
    Windows/macOS 'tp.nc' y 'TP.nc' serían el mismo archivo.
    """
    por_slug: dict[str, list[Capa]] = {}
    for capa in capas:
        por_slug.setdefault(_slug(capa, agrupacion), []).append(capa)
    usados: set[str] = set()
    plan: dict[str, list[Capa]] = {}
    for slug, grupo in por_slug.items():
        final, n = slug, 1
        while final.casefold() in usados:
            n += 1
            final = f"{slug}_{n}"
        usados.add(final.casefold())
        nombre = f"{prefijo}_{fecha}_{ciclo}Z_{final}"
        # Solo "capa" tiene un mensaje GRIB inequívoco por archivo.
        if agrupacion == "capa" and mensajes and grupo[0].nombre in mensajes:
            nombre += f"_msg{mensajes[grupo[0].nombre]}"
        plan[f"{nombre}.nc"] = grupo
    return plan


def partir_en_lotes(plan: dict[str, list[Capa]], maximo: int) -> list[dict[str, list[Capa]]]:
    """Trozos de como mucho `maximo` archivos abiertos a la vez."""
    nombres = list(plan)
    return [{n: plan[n] for n in nombres[i:i + maximo]} for i in range(0, len(nombres), maximo)]
