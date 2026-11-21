"""Lectura de las capas NetCDF (variable x nivel) y del respaldo compacto de perfiles.

Fuentes, en orden de preferencia (igual que las tablas):
  1. Capas NetCDF del ciclo en ``___Data/___NC/AAAAMMDD/HH`` (siempre con los puntos actuales).
  2. Respaldo ``___Data/___Historico_Corte/AAAAMMDD_HHZ.parquet`` (perfiles ya extraídos).

El respaldo se puede rehacer en cualquier momento a partir de los NetCDF con
``python _0_Visor/archivar_corte.py --todos`` (por ejemplo, si cambian los puntos).
Los valores se guardan en la unidad definida en ``capas`` de variables.json (°C, %, m/s).
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

import datos_ciclos as dc
from datos_ciclos import Punto

from .config import ConfigCorte

log = logging.getLogger(__name__)

DIR_PERFILES = dc.RAIZ_PROYECTO / "___Data" / "___Historico_Corte"
COLUMNAS_PERFIL = ("Ciclo", "FechaHoraUTC", "Área", "Punto", "Latitud", "Longitud",
                   "Capa", "Nivel_hPa", "Valor", "Unidad", "ArchivoNetCDF")
_ARCHIVO_CAPA = re.compile(r"_([A-Za-z0-9]+)_(\d+)hPa(?:_msg\d+)?\.nc$")


def nombre_capa(prefijo: str, nivel: int) -> str:
    return f"{prefijo}_{nivel}hPa"


# --------------------------------------------------------------------------- localizar archivos
def indice_capas_nc(clave_ciclo: str) -> dict[tuple[str, int], Path]:
    """{(prefijo, nivel hPa): archivo} de las capas NetCDF de ese ciclo (una sola lectura de la carpeta)."""
    fecha, ciclo = clave_ciclo.split("_")
    carpeta = dc.DIR_NC / fecha / ciclo
    if not carpeta.is_dir():
        return {}
    indice: dict[tuple[str, int], Path] = {}
    for archivo in sorted(carpeta.glob("*hPa*.nc")):
        m = _ARCHIVO_CAPA.search(archivo.name)
        if m:
            indice.setdefault((m.group(1), int(m.group(2))), archivo)
    return indice


def ruta_perfiles(clave_ciclo: str) -> Path | None:
    archivo = DIR_PERFILES / f"{clave_ciclo}Z.parquet"
    return archivo if archivo.is_file() else None


def listar_ciclos_corte(cfg: ConfigCorte) -> list[str]:
    """Ciclos con datos para la pestaña (capas NetCDF o respaldo), del más reciente al más antiguo."""
    ciclos: set[str] = set()
    if dc.DIR_NC.is_dir():
        for carpeta in dc.DIR_NC.glob("*/*"):
            if carpeta.is_dir() and carpeta.parent.name.isdigit() and carpeta.name in dc.CICLOS_VALIDOS:
                clave = f"{carpeta.parent.name}_{carpeta.name}"
                if any((pre, n) in indice_capas_nc(clave) for pre, n in cfg.todas_las_capas[:6]):
                    ciclos.add(clave)
    if DIR_PERFILES.is_dir():
        for archivo in DIR_PERFILES.glob("*_??Z.parquet"):
            ciclos.add(archivo.name.removesuffix("Z.parquet"))
    return sorted(ciclos, reverse=True)


def firma_fuente(clave_ciclo: str) -> float:
    """Cambia cuando cambian los archivos del ciclo (sirve de clave de caché)."""
    fechas = [a.stat().st_mtime for a in indice_capas_nc(clave_ciclo).values()]
    respaldo = ruta_perfiles(clave_ciclo)
    if respaldo:
        fechas.append(respaldo.stat().st_mtime)
    return max(fechas, default=0.0)


# --------------------------------------------------------------------------- lectura NetCDF
def _leer_capa(ruta: Path, nombre_var: str, puntos: Sequence[Punto]) -> tuple[pd.DatetimeIndex, np.ndarray]:
    """Serie de cada punto (celda más cercana) de una capa: (horas UTC, matriz horas x puntos).

    Solo se lee el rectángulo de la malla que contiene a los puntos, así el consumo de memoria
    no depende del tamaño del área descargada. Los puntos fuera de la malla quedan en NaN.
    """
    from netCDF4 import Dataset

    with Dataset(ruta, "r") as ds:
        base = dc.inicio_ciclo(ds)
        leads = np.asarray(ds.variables["forecast_hour"][:], dtype=float)
        latitudes = np.asarray(ds.variables["latitude"][:], dtype=float)
        longitudes = ((np.asarray(ds.variables["longitude"][:], dtype=float) + 180) % 360) - 180
        variable = ds.variables.get(nombre_var)
        if variable is None:     # nombre distinto: la única variable con tres dimensiones
            tridimensionales = [v for v in ds.variables.values() if len(v.dimensions) == 3]
            if len(tridimensionales) != 1:
                raise ValueError(f"{ruta.name}: no se encontró la variable {nombre_var}.")
            variable = tridimensionales[0]
        iy, ix, fuera = dc.puntos_fuera_de_malla(latitudes, longitudes, puntos)
        dc.avisar_puntos_fuera(fuera, puntos, ruta.name)
        valores = np.full((len(leads), len(puntos)), np.nan)
        dentro = ~fuera
        if dentro.any():
            y0, y1, x0, x1 = iy[dentro].min(), iy[dentro].max(), ix[dentro].min(), ix[dentro].max()
            bloque = np.ma.asarray(variable[:, y0:y1 + 1, x0:x1 + 1], dtype=float).filled(np.nan)
            valores[:, dentro] = bloque[:, iy[dentro] - y0, ix[dentro] - x0]
    horas = pd.DatetimeIndex([base + pd.Timedelta(hours=float(h)) for h in leads])
    return horas, valores


def extraer_perfiles_nc(clave_ciclo: str, cfg: ConfigCorte, puntos: Sequence[Punto],
                        prefijos: Sequence[str] | None = None) -> tuple[pd.DataFrame, list[str]]:
    """Perfiles de los puntos desde las capas NetCDF: (tabla larga, capas faltantes).

    Columnas de la tabla: Ciclo, FechaHoraUTC, Área, Punto, Latitud, Longitud, Capa, Nivel_hPa,
    Valor (en la unidad guardada), Unidad y ArchivoNetCDF.
    """
    indice = indice_capas_nc(clave_ciclo)
    partes: list[pd.DataFrame] = []
    faltantes: list[str] = []
    areas = np.array([p.area for p in puntos])
    nombres = np.array([p.punto for p in puntos])
    lats = np.array([p.lat for p in puntos], dtype=float)
    lons = np.array([p.lon for p in puntos], dtype=float)
    for prefijo, nivel in cfg.todas_las_capas:
        if prefijos is not None and prefijo not in prefijos:
            continue
        ruta = indice.get((prefijo, nivel))
        if ruta is None:
            faltantes.append(nombre_capa(prefijo, nivel))
            continue
        capa = cfg.capas[prefijo]
        horas, crudo = _leer_capa(ruta, nombre_capa(prefijo, nivel), puntos)
        valores = crudo * capa.factor + capa.desplazamiento
        n_t, n_p = valores.shape
        fechas = pd.DatetimeIndex(np.tile(horas.tz_localize(None).to_numpy(), n_p)).tz_localize("UTC")
        tabla = pd.DataFrame({
            "Ciclo": clave_ciclo + "Z", "FechaHoraUTC": fechas,
            "Área": np.repeat(areas, n_t), "Punto": np.repeat(nombres, n_t),
            "Latitud": np.repeat(lats, n_t), "Longitud": np.repeat(lons, n_t),
            "Capa": prefijo, "Nivel_hPa": np.int16(nivel), "Valor": valores.T.reshape(-1),
            "Unidad": capa.unidad, "ArchivoNetCDF": ruta.name})
        partes.append(tabla[np.isfinite(tabla["Valor"])])
    if not partes:
        return pd.DataFrame(columns=list(COLUMNAS_PERFIL)), faltantes
    return pd.concat(partes, ignore_index=True)[list(COLUMNAS_PERFIL)], faltantes


# --------------------------------------------------------------------------- respaldo (parquet)
def guardar_perfiles_ciclo(clave_ciclo: str, cfg: ConfigCorte, puntos: Sequence[Punto]) -> tuple[Path, int, list[str]]:
    """Guarda en ``___Historico_Corte`` los perfiles de todos los puntos. Devuelve (archivo, filas, capas faltantes).

    Falla con FileNotFoundError si el ciclo no tiene ninguna capa (no deja archivos vacíos).
    """
    tabla, faltantes = extraer_perfiles_nc(clave_ciclo, cfg, puntos)
    if tabla.empty:
        raise FileNotFoundError(
            f"No hay capas NetCDF del ciclo {clave_ciclo} en {dc.DIR_NC} (faltan {len(faltantes)} de "
            f"{len(cfg.todas_las_capas)}).")
    DIR_PERFILES.mkdir(parents=True, exist_ok=True)
    destino = DIR_PERFILES / f"{clave_ciclo}Z.parquet"
    temporal = destino.with_name(destino.name + ".part")
    try:
        tabla.to_parquet(temporal, engine="pyarrow", compression="zstd", index=False)
        os.replace(temporal, destino)
    finally:
        temporal.unlink(missing_ok=True)
    return destino, len(tabla), faltantes


def _leer_perfil_parquet(ruta: Path, area: str, punto: str) -> pd.DataFrame:
    tabla = pd.read_parquet(ruta, engine="pyarrow",
                            filters=[("Área", "==", area), ("Punto", "==", punto)])
    tabla["FechaHoraUTC"] = pd.to_datetime(tabla["FechaHoraUTC"], utc=True)
    return tabla


# --------------------------------------------------------------------------- perfil de un punto
@dataclass(frozen=True)
class PerfilPunto:
    tabla: pd.DataFrame            # misma forma que extraer_perfiles_nc
    fuente: str                    # "NetCDF" o "respaldo"
    capas_faltantes: tuple[str, ...]


def cargar_perfil_punto(clave_ciclo: str, cfg: ConfigCorte, punto: Punto) -> PerfilPunto:
    """Perfil completo de un punto: de las capas NetCDF si existen y, si no, del respaldo."""
    if indice_capas_nc(clave_ciclo):
        tabla, faltantes = extraer_perfiles_nc(clave_ciclo, cfg, [punto])
        if not tabla.empty:
            return PerfilPunto(tabla, "NetCDF", tuple(faltantes))
    respaldo = ruta_perfiles(clave_ciclo)
    if respaldo is not None:
        return PerfilPunto(_leer_perfil_parquet(respaldo, punto.area, punto.punto), "respaldo", ())
    return PerfilPunto(pd.DataFrame(columns=list(COLUMNAS_PERFIL)), "ninguna", ())
