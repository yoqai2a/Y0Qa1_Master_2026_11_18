"""Lectura de los fNNN en dos fases (cada una independiente por archivo, apta para procesos paralelos).

1. `escanear_lead`: recorre el GRIB UNA vez, identifica los mensajes por nombre y
   guarda dónde está cada capa (posición y tamaño en bytes).
2. `decodificar`: lee solo esos bytes y los decodifica.

Iterar los ~700 mensajes de un fNNN cuesta ~100× más que decodificar los pocos que
se necesitan, por eso las pasadas posteriores no vuelven a recorrer el archivo.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .variables import Capa, clave_primaria, mismo_nivel

Posicion = tuple[int, int]                              # (offset, bytes) del mensaje en el archivo
Campos = dict[str, tuple[np.ndarray, float, float]]     # nombre -> (matriz float32, mínimo, máximo)


@dataclass
class ContextoLectura:
    """Datos de solo lectura que necesita cada proceso trabajador."""
    indice: dict[tuple, list[Capa]]
    lat1d: np.ndarray
    lon1d: np.ndarray


@dataclass
class Escaneo:
    """Resultado de recorrer un fNNN."""
    mapa: dict[str, Posicion] = field(default_factory=dict)
    mensajes: dict[str, int] = field(default_factory=dict)  # capa -> número msg GRIB
    duplicados: list[str] = field(default_factory=list)   # capas con varios mensajes candidatos


def _valor(grb, clave: str):
    try:
        if not grb.valid_key(clave):
            return None
        valor = grb[clave]
        if isinstance(valor, (int, float)) and grb.is_missing(clave):
            return None
        return valor
    except Exception:
        return None


def _nivel_superficie(grb, numero: int):
    """Valor escalado de la 1.ª o 2.ª superficie fija (top/bottom del catálogo)."""
    sufijo = "First" if numero == 1 else "Second"
    tipo = _valor(grb, f"typeOf{sufijo}FixedSurface")
    if tipo is None or tipo == 255:
        return None
    valor = _valor(grb, f"scaledValueOf{sufijo}FixedSurface")
    escala = _valor(grb, f"scaleFactorOf{sufijo}FixedSurface")
    if valor is None or escala is None or escala == 255:
        return None
    try:
        return round(float(valor) * (10.0 ** -int(escala)), 10)
    except (OverflowError, TypeError, ValueError):
        return None


def _clave_mensaje(grb) -> tuple | None:
    try:
        return clave_primaria(grb.shortName, grb.typeOfLevel, grb.level, grb.stepType)
    except (AttributeError, KeyError, RuntimeError, TypeError, ValueError):
        return None


def _cumple(capa: Capa, grb, posicion: int) -> bool:
    """Filtros finos: top/bottom, intervalo, ocurrencia y parámetro GRIB2."""
    if capa.top is not None and not mismo_nivel(_nivel_superficie(grb, 1), capa.top):
        return False
    if capa.bottom is not None and not mismo_nivel(_nivel_superficie(grb, 2), capa.bottom):
        return False
    if capa.desde_inicio and _valor(grb, "startStep") != 0:
        return False
    if capa.ocurrencia is not None and capa.ocurrencia != posicion:
        return False
    if capa.parametro is not None:
        real = tuple(_valor(grb, k) for k in ("discipline", "parameterCategory", "parameterNumber"))
        if real != capa.parametro:
            return False
    return True


def _a_float32(valores) -> np.ndarray:
    if np.ma.isMaskedArray(valores):
        valores = valores.astype("float32").filled(np.nan)
    return np.ascontiguousarray(valores, dtype="float32")


def posiciones_mensajes(ruta: Path) -> list[Posicion]:
    """(offset, bytes) de cada mensaje GRIB2 leyendo solo la cabecera de cada uno."""
    posiciones: list[Posicion] = []
    total = ruta.stat().st_size
    with ruta.open("rb") as f:
        pos = 0
        while pos < total:
            f.seek(pos)
            cabecera = f.read(16)
            if len(cabecera) < 16 or cabecera[:4] != b"GRIB" or cabecera[7] != 2:
                raise RuntimeError(f"{ruta.name}: se esperaba GRIB2 contiguo (mensaje {len(posiciones) + 1}).")
            largo = int.from_bytes(cabecera[8:16], "big")
            posiciones.append((pos, largo))
            pos += largo
    return posiciones


def leer_malla(ruta: Path) -> tuple[np.ndarray, np.ndarray]:
    """Latitudes y longitudes 1D de la malla (debe ser regular lat/lon)."""
    import pygrib
    with pygrib.open(str(ruta)) as grbs:
        lats, lons = grbs.message(1).latlons()
    lat1d, lon1d = lats[:, 0], lons[0, :]
    if not (np.allclose(lats, lat1d[:, None], atol=1e-6) and np.allclose(lons, lon1d[None, :], atol=1e-6)):
        raise RuntimeError("La malla del GRIB no es regular lat/lon; no está soportada.")
    return lat1d.astype("float64"), lon1d.astype("float64")


# ----------------------------------------------------------------------------
# Fase 1: escaneo
# ----------------------------------------------------------------------------
def escanear_lead(ctx: ContextoLectura, ruta: Path) -> Escaneo:
    """Ubica en el fNNN todas las capas configuradas, sin decodificar valores."""
    import pygrib

    posiciones = posiciones_mensajes(ruta)
    escaneo = Escaneo()
    vistas: dict[tuple, int] = {}
    contados = 0
    with pygrib.open(str(ruta)) as grbs:
        for grb in grbs:
            contados += 1
            clave = _clave_mensaje(grb)
            candidatas = ctx.indice.get(clave) if clave is not None else None
            if not candidatas:
                continue
            vistas[clave] = posicion = vistas.get(clave, 0) + 1
            capa = next((c for c in candidatas if _cumple(c, grb, posicion)), None)
            if capa is None:
                continue
            ubicacion = posiciones[grb.messagenumber - 1]
            if capa.nombre in escaneo.mapa:
                # GFS repite campos (p. ej. tp 0-6 dos veces en f006): se aplica la política del campo.
                if capa.duplicados == "error":
                    raise RuntimeError(
                        f"{ruta.name}: dos mensajes coinciden con {capa.nombre}; "
                        "añade un filtro (intervalo, ocurrencia o parametro) o usa duplicados = \"ultimo\"."
                    )
                escaneo.duplicados.append(capa.nombre)
                if capa.duplicados == "primero":
                    continue
            escaneo.mapa[capa.nombre] = ubicacion
            escaneo.mensajes[capa.nombre] = grb.messagenumber
    if contados != len(posiciones):
        raise RuntimeError(f"{ruta.name}: mensajes multicampo no soportados "
                           f"({contados} campos en {len(posiciones)} mensajes).")
    return escaneo


# ----------------------------------------------------------------------------
# Fase 2: decodificación selectiva
# ----------------------------------------------------------------------------
def decodificar(ctx: ContextoLectura, ruta: Path, seleccion: dict[str, Posicion]) -> Campos:
    """Decodifica solo los mensajes pedidos (nombre -> posición) leyendo sus bytes."""
    import pygrib

    campos: Campos = {}
    forma = (len(ctx.lat1d), len(ctx.lon1d))
    malla_validada = False
    with ruta.open("rb") as archivo:
        for nombre, (offset, largo) in sorted(seleccion.items(), key=lambda x: x[1][0]):
            archivo.seek(offset)
            grb = pygrib.fromstring(archivo.read(largo))
            matriz = _a_float32(grb.values)
            if matriz.shape != forma:
                raise RuntimeError(f"La forma de la malla cambió en {ruta.name} ({nombre}).")
            if not malla_validada:
                lats, lons = grb.latlons()
                if not (np.allclose(lats[:, 0], ctx.lat1d, atol=1e-6)
                        and np.allclose(lons[0, :], ctx.lon1d, atol=1e-6)):
                    raise RuntimeError(f"La malla cambió en {ruta.name}.")
                malla_validada = True
            finitos = np.isfinite(matriz)
            if finitos.any():
                minimo, maximo = float(matriz[finitos].min()), float(matriz[finitos].max())
            else:
                minimo = maximo = float("nan")
            campos[nombre] = (matriz, minimo, maximo)
    return campos


# ----------------------------------------------------------------------------
# Procesos trabajadores (multiprocessing con 'spawn': funciones a nivel de módulo)
# ----------------------------------------------------------------------------
_CTX: ContextoLectura | None = None


def iniciar_trabajador(ctx: ContextoLectura) -> None:
    global _CTX
    _CTX = ctx


def tarea_escanear(ruta: str) -> Escaneo:
    assert _CTX is not None, "trabajador sin inicializar"
    return escanear_lead(_CTX, Path(ruta))


def tarea_decodificar(ruta: str, seleccion: dict[str, Posicion]) -> Campos:
    assert _CTX is not None, "trabajador sin inicializar"
    return decodificar(_CTX, Path(ruta), seleccion)


# ----------------------------------------------------------------------------
# Inventario: ayuda para añadir variables al TOML
# ----------------------------------------------------------------------------
def inventario(ruta: Path) -> list[dict[str, Any]]:
    import pygrib
    filas = []
    with pygrib.open(str(ruta)) as grbs:
        for grb in grbs:
            parametro = ".".join(str(_valor(grb, k)) for k in ("discipline", "parameterCategory", "parameterNumber"))
            filas.append({
                "msg": grb.messagenumber,
                "shortName": _valor(grb, "shortName"),
                "name": _valor(grb, "name"),
                "units": _valor(grb, "units"),
                "tipoNivel": _valor(grb, "typeOfLevel"),
                "level": _valor(grb, "level"),
                "top": _nivel_superficie(grb, 1),
                "bottom": _nivel_superficie(grb, 2),
                "stepType": _valor(grb, "stepType"),
                "stepRange": _valor(grb, "stepRange"),
                "parametro": parametro,
            })
    return filas
