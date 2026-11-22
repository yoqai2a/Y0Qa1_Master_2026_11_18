"""Utilidades de mallas NetCDF compartidas por las pestañas del visor y por los programas de archivo.

Reúne lo que necesitan por igual Tablas y Corte temporal: los puntos, el inicio de un ciclo y la
búsqueda de la celda más cercana (con la comprobación de que el punto esté dentro de la malla).
No depende de Streamlit ni de pandas.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple, Sequence

import numpy as np

log = logging.getLogger(__name__)

RAIZ_PROYECTO = Path(__file__).resolve().parent.parent
DIR_NC = RAIZ_PROYECTO / "___Data" / "___NC"
UTC = timezone.utc
CICLOS_VALIDOS = ("00", "06", "12", "18")


class Punto(NamedTuple):
    area: str
    punto: str
    lat: float
    lon: float


@lru_cache(maxsize=8)
def _puntos_desde(ruta: str, mtime_ns: int) -> tuple[Punto, ...]:
    datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
    return tuple(
        Punto(area, nombre, float(coord["lat"]), float(coord["lon"]))
        for area, puntos in datos.items()
        for nombre, coord in puntos.items()
    )


def cargar_puntos(ruta: Path) -> tuple[Punto, ...]:
    """Puntos de un archivo JSON (área -> punto -> lat/lon). Se relee solo si el archivo cambió."""
    return _puntos_desde(str(ruta), Path(ruta).stat().st_mtime_ns)


def inicio_ciclo(ds) -> datetime:
    """Inicio del ciclo (UTC con zona) leído de los atributos globales del NetCDF."""
    fecha = str(ds.getncattr("initialization_date"))
    ciclo = str(ds.getncattr("initialization_cycle_utc")).replace("Z", "")
    return datetime.strptime(fecha + ciclo.zfill(2), "%Y%m%d%H").replace(tzinfo=UTC)


def indices_mas_cercanos(valores: np.ndarray, objetivos: np.ndarray, circular: bool) -> tuple[np.ndarray, np.ndarray]:
    """Índice de la celda más cercana a cada objetivo y la distancia (en grados) a esa celda."""
    diferencia = valores[None, :] - objetivos[:, None]
    if circular:
        diferencia = ((diferencia + 180) % 360) - 180
    distancia = np.abs(diferencia)
    indices = np.nanargmin(distancia, axis=1)
    return indices, distancia[np.arange(len(objetivos)), indices]


def _paso_malla(valores: np.ndarray) -> float:
    return float(np.median(np.abs(np.diff(valores)))) if len(valores) > 1 else 0.0


def puntos_fuera_de_malla(latitudes: np.ndarray, longitudes: np.ndarray,
                          puntos: Sequence[Punto]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Índices (iy, ix) de la celda más cercana y una máscara con los puntos fuera de la malla.

    Un punto está fuera si la celda más cercana queda a más de una celda de distancia: sin
    esta comprobación se usaría en silencio la celda del borde, que no representa al punto.
    """
    lat = np.array([p.lat for p in puntos], dtype=float)
    lon = ((np.array([p.lon for p in puntos], dtype=float) + 180) % 360) - 180
    iy, dlat = indices_mas_cercanos(latitudes, lat, circular=False)
    ix, dlon = indices_mas_cercanos(longitudes, lon, circular=True)
    fuera = (dlat > _paso_malla(latitudes)) | (dlon > _paso_malla(longitudes))
    return iy, ix, fuera


_AVISOS_EMITIDOS: set[tuple] = set()


def avisar_puntos_fuera(fuera: np.ndarray, puntos: Sequence[Punto], archivo: str) -> None:
    """Avisa en el registro (una sola vez por conjunto de puntos) de los que están fuera de la malla."""
    if not fuera.any():
        return
    omitidos = tuple(f"{p.area}/{p.punto}" for p, f in zip(puntos, fuera) if f)
    if omitidos in _AVISOS_EMITIDOS:
        return
    _AVISOS_EMITIDOS.add(omitidos)
    log.warning("AVISO: %d punto(s) quedan fuera de la malla de %s (y de las demás capas del ciclo) y se omiten: %s. "
                "Revisa el área de descarga (__Configuracion_Fnnn.toml).", len(omitidos), archivo, ", ".join(omitidos))
