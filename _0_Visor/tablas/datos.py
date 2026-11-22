"""Datos de la pestaña Tablas: ciclos, NetCDF, histórico y cierres.

No depende de Streamlit (lo usa también el workflow de GitHub Actions). Lo que comparte con otras
pestañas (puntos, inicio de ciclo, celda más cercana) está en ``_Comun/malla_nc.py``.

Los valores se normalizan siempre a una tabla de series con las columnas
``FechaHoraUTC`` (UTC con zona), ``Área``, ``Punto``, ``Latitud``, ``Longitud`` y ``Valor``
(en la unidad de almacenamiento de cada variable, ver ``variables``).
La tabla sale igual ya sea que provenga de un NetCDF o del histórico guardado.
"""
from __future__ import annotations

import copy
import json
import logging
import os
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

from _Comun import malla_nc as malla
from _Comun.malla_nc import CICLOS_VALIDOS, Punto, inicio_ciclo, puntos_fuera_de_malla, avisar_puntos_fuera

from .variables import HORAS_CIERRE, VARIABLES_METEO, VariableMeteo

log = logging.getLogger(__name__)

RAIZ_PROYECTO = malla.RAIZ_PROYECTO
CARPETA_CONFIG = Path(__file__).resolve().parent / "configuracion"


DIR_HISTORICO = RAIZ_PROYECTO / "___Data" / "___Historico"
ARCHIVO_PUNTOS = CARPETA_CONFIG / "Puntos.json"
ARCHIVO_CIERRES = CARPETA_CONFIG / "cierres_tablas.json"

COLUMNAS_HISTORICO = ("Ciclo", "FechaHoraUTC", "Área", "Punto", "Latitud", "Longitud",
                      "Variable", "Valor", "Unidad", "ArchivoNetCDF")
EXTENSIONES_HISTORICO = (".parquet", ".csv.gz", ".csv")
FORMATOS_HISTORICO = ("parquet", "csv")




# --------------------------------------------------------------------------- configuración JSON




@lru_cache(maxsize=16)
def _json_desde(ruta: str, mtime_ns: int) -> dict:
    return json.loads(Path(ruta).read_text(encoding="utf-8"))


def leer_json_cacheado(ruta: Path) -> dict:
    """JSON de configuración con caché por fecha de modificación (devuelve una copia)."""
    return copy.deepcopy(_json_desde(str(ruta), ruta.stat().st_mtime_ns))


def cargar_cierres() -> dict[str, str]:
    try:
        datos = json.loads(ARCHIVO_CIERRES.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    if not isinstance(datos, dict):
        return {}
    return {str(fecha): str(hora) for fecha, hora in datos.items() if str(hora) in HORAS_CIERRE}


def cargar_cierre_global() -> str:
    return cargar_cierres().get("_global", "12")


def guardar_cierre_global(hora: str) -> None:
    cierres = cargar_cierres()
    cierres["_global"] = hora
    temporal = ARCHIVO_CIERRES.with_name(ARCHIVO_CIERRES.name + ".part")
    temporal.write_text(json.dumps(cierres, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporal, ARCHIVO_CIERRES)


# --------------------------------------------------------------------------- ciclos y archivos
def es_historico(ruta: str | Path) -> bool:
    return str(ruta).endswith(EXTENSIONES_HISTORICO)


def _clave_de_historico(archivo: Path) -> str | None:
    base = archivo.name
    for extension in EXTENSIONES_HISTORICO:
        if base.endswith(extension):
            base = base.removesuffix(extension)
            break
    else:
        return None
    if not base.endswith("Z"):
        return None
    clave = base[:-1]
    try:
        fecha, ciclo = clave.split("_")
        datetime.strptime(fecha, "%Y%m%d")
    except ValueError:
        return None
    return clave if ciclo in CICLOS_VALIDOS else None


def ruta_historico(clave_ciclo: str) -> Path | None:
    """Histórico guardado del ciclo (Parquet preferido; también lee CSV comprimido o plano)."""
    for extension in EXTENSIONES_HISTORICO:
        archivo = DIR_HISTORICO / f"{clave_ciclo}Z{extension}"
        if archivo.is_file():
            return archivo
    return None


def listar_ciclos() -> list[tuple[str, Path]]:
    """Ciclos disponibles en NetCDF locales o en históricos publicados, del más reciente al más antiguo."""
    ciclos: dict[str, Path] = {}
    if DIR_HISTORICO.is_dir():
        for archivo in DIR_HISTORICO.glob("*_??Z.*"):
            clave = _clave_de_historico(archivo)
            if clave:
                ciclos[clave] = archivo
    if malla.DIR_NC.is_dir():
        for archivo in malla.DIR_NC.glob("*/*/*gust*.nc"):
            fecha, ciclo = archivo.parent.parent.name, archivo.parent.name
            try:
                datetime.strptime(fecha, "%Y%m%d")
            except ValueError:
                continue
            if ciclo in CICLOS_VALIDOS:
                ciclos[f"{fecha}_{ciclo}"] = archivo
    return sorted(ciclos.items(), reverse=True)


def ruta_nc(clave_ciclo: str, variable: str) -> Path | None:
    """Archivo NetCDF de la variable en el ciclo, o None."""
    fecha, ciclo = clave_ciclo.split("_")
    carpeta = malla.DIR_NC / fecha / ciclo
    for patron in VARIABLES_METEO[variable].patrones_archivo:
        coincidencias = sorted(carpeta.glob(patron))
        if coincidencias:
            return coincidencias[0]
    return None


def ruta_variable(clave_ciclo: str, variable: str) -> Path | None:
    """Fuente de datos de la variable: su NetCDF o, si no existe, el histórico del ciclo."""
    return ruta_nc(clave_ciclo, variable) or ruta_historico(clave_ciclo)


# --------------------------------------------------------------------------- lectura NetCDF


def _buscar_variable_nc(ds, definicion: VariableMeteo, nombre_archivo: str):
    for nombre, variable in ds.variables.items():
        if (nombre.casefold().startswith(definicion.prefijos_nc)
                or str(getattr(variable, "GRIB_shortName", "")).casefold() == definicion.shortname_nc):
            return variable
    raise ValueError(f"No se encontró la variable {definicion.clave} dentro de {nombre_archivo}.")












def horas_validas_nc(ruta: Path) -> list[datetime]:
    """Horas válidas (UTC) del eje de pronóstico del NetCDF."""
    from netCDF4 import Dataset

    with Dataset(ruta, "r") as ds:
        base = inicio_ciclo(ds)
        leads = np.asarray(ds.variables["forecast_hour"][:], dtype=float)
    return [base + timedelta(hours=float(lead)) for lead in leads]


def extraer_series_nc(ruta: Path, clave: str, puntos: Sequence[Punto]) -> pd.DataFrame:
    """Serie temporal de cada punto (celda de malla más cercana), en la unidad de almacenamiento.

    Se lee un mapa horario a la vez y se indexan todos los puntos juntos, así el consumo de
    memoria no depende del tamaño de la malla.
    """
    from netCDF4 import Dataset

    definicion = VARIABLES_METEO[clave]
    with Dataset(ruta, "r") as ds:
        base = inicio_ciclo(ds)
        for nombre in ("latitude", "longitude", "forecast_hour"):
            if nombre not in ds.variables:
                raise ValueError(f"{ruta.name} no contiene {nombre}.")
        leads = np.asarray(ds.variables["forecast_hour"][:], dtype=float)
        if not leads.size:
            raise ValueError("El archivo no contiene horas de pronóstico.")
        latitudes = np.asarray(ds.variables["latitude"][:], dtype=float)
        longitudes = ((np.asarray(ds.variables["longitude"][:], dtype=float) + 180) % 360) - 180
        variable = _buscar_variable_nc(ds, definicion, ruta.name)

        lat_objetivo = np.array([p.lat for p in puntos], dtype=float)
        iy, ix, fuera = puntos_fuera_de_malla(latitudes, longitudes, puntos)
        avisar_puntos_fuera(fuera, puntos, ruta.name)

        crudo = np.full((len(leads), len(puntos)), np.nan)
        for t in range(len(leads)):
            mapa = np.ma.asarray(variable[t, :, :], dtype=float).filled(np.nan)
            crudo[t, :] = mapa[iy, ix]
        crudo[:, fuera] = np.nan      # los puntos fuera de la malla no tienen dato

    valores = crudo * definicion.factor_nc + definicion.desplazamiento_nc
    horas = pd.DatetimeIndex([base + timedelta(hours=float(h)) for h in leads])
    n_t, n_p = valores.shape
    fechas = pd.DatetimeIndex(np.tile(horas.tz_localize(None).to_numpy(), n_p)).tz_localize("UTC")
    tabla = pd.DataFrame({
        "FechaHoraUTC": fechas,
        "Área": np.repeat([p.area for p in puntos], n_t),
        "Punto": np.repeat([p.punto for p in puntos], n_t),
        "Latitud": np.repeat(lat_objetivo, n_t),
        "Longitud": np.repeat([p.lon for p in puntos], n_t),
        "Valor": valores.T.reshape(-1),        # punto por punto, cada uno en orden temporal
    })
    return tabla[np.isfinite(tabla["Valor"])].reset_index(drop=True)


# --------------------------------------------------------------------------- lectura del histórico
def _a_utc(columna: pd.Series) -> pd.Series:
    return pd.to_datetime(columna, utc=True)


def leer_series_historico(ruta: Path, clave: str) -> pd.DataFrame:
    """Serie de una variable desde un histórico (Parquet, CSV comprimido o CSV)."""
    etiqueta = VARIABLES_METEO[clave].etiqueta_historico
    columnas = ["FechaHoraUTC", "Área", "Punto", "Latitud", "Longitud", "Variable", "Valor"]
    if str(ruta).endswith(".parquet"):
        datos = pd.read_parquet(ruta, columns=columnas, filters=[("Variable", "==", etiqueta)])
    else:
        datos = pd.read_csv(ruta, compression="infer", usecols=columnas)
        datos = datos[datos["Variable"] == etiqueta]
    faltan = set(columnas) - set(datos.columns)
    if faltan:
        raise ValueError("El histórico no tiene las columnas requeridas: " + ", ".join(sorted(faltan)))
    if datos.empty:
        raise ValueError(f"El archivo histórico no tiene datos para {etiqueta}.")
    datos = datos.drop(columns="Variable")
    datos["FechaHoraUTC"] = _a_utc(datos["FechaHoraUTC"])
    datos["Valor"] = pd.to_numeric(datos["Valor"], errors="coerce")
    return datos.dropna(subset=["FechaHoraUTC", "Valor"]).reset_index(drop=True)


def limites_historico(ruta: Path) -> tuple[datetime, datetime] | None:
    """Primera y última hora del histórico (todas las variables)."""
    if str(ruta).endswith(".parquet"):
        horas = pd.read_parquet(ruta, columns=["FechaHoraUTC"])["FechaHoraUTC"]
    else:
        horas = pd.read_csv(ruta, compression="infer", usecols=["FechaHoraUTC"])["FechaHoraUTC"]
    horas = _a_utc(horas).dropna()
    if horas.empty:
        return None
    return horas.min().to_pydatetime(), horas.max().to_pydatetime()


def cargar_series(ruta: Path, clave: str, puntos: Sequence[Punto]) -> pd.DataFrame:
    """Tabla de series de la variable, venga de un NetCDF o de un histórico."""
    if es_historico(ruta):
        return leer_series_historico(ruta, clave)
    return extraer_series_nc(ruta, clave, puntos)


# --------------------------------------------------------------------------- escritura del histórico
def guardar_historico_ciclo(clave_ciclo: str, puntos: Sequence[Punto],
                            formato: str = "parquet") -> tuple[Path, int, list[str]]:
    """Guarda las series de todas las variables del ciclo (para consultarlas sin los NetCDF).

    Devuelve (archivo, filas, etiquetas de variables sin NetCDF); falla con FileNotFoundError si
    el ciclo no tiene ningún NetCDF. ``formato``: "parquet"
    (por defecto, mucho más compacto) o "csv" (CSV comprimido con gzip, formato anterior).
    """
    if formato not in FORMATOS_HISTORICO:
        raise ValueError(f"Formato de histórico desconocido: {formato!r} (use {FORMATOS_HISTORICO}).")
    partes: list[pd.DataFrame] = []
    faltantes: list[str] = []
    for definicion in VARIABLES_METEO.values():
        ruta = ruta_nc(clave_ciclo, definicion.clave)
        if ruta is None:
            faltantes.append(definicion.etiqueta_historico)
            continue
        tabla = extraer_series_nc(ruta, definicion.clave, puntos)
        tabla.insert(0, "Ciclo", clave_ciclo + "Z")
        tabla["Variable"] = definicion.etiqueta_historico
        tabla["Unidad"] = definicion.unidad_historico
        tabla["ArchivoNetCDF"] = ruta.name
        partes.append(tabla)
    if not partes:   # no se deja un histórico vacío
        raise FileNotFoundError(
            f"No hay NetCDF del ciclo {clave_ciclo} en {malla.DIR_NC}; faltan: " + ", ".join(faltantes))
    historico = pd.concat(partes, ignore_index=True)[list(COLUMNAS_HISTORICO)]

    DIR_HISTORICO.mkdir(parents=True, exist_ok=True)
    extension = ".parquet" if formato == "parquet" else ".csv.gz"
    destino = DIR_HISTORICO / f"{clave_ciclo}Z{extension}"
    temporal = destino.with_name(destino.name + ".part")
    try:
        if formato == "parquet":
            historico.to_parquet(temporal, engine="pyarrow", compression="zstd", index=False)
        else:
            salida = historico.copy()
            salida["FechaHoraUTC"] = salida["FechaHoraUTC"].dt.strftime("%Y-%m-%d %H:%M")
            salida.to_csv(temporal, index=False, compression={"method": "gzip"}, encoding="utf-8-sig")
        os.replace(temporal, destino)
    finally:
        temporal.unlink(missing_ok=True)
    return destino, len(historico), faltantes


def cargar_puntos(ruta: Path | None = None) -> tuple[Punto, ...]:
    """Puntos de Tablas (``configuracion/Puntos.json``) o de ``ruta``."""
    return malla.cargar_puntos(ruta or ARCHIVO_PUNTOS)
