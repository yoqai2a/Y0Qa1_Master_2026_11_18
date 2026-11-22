"""Carga y validación de __Configuracion_NC.toml."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - Python 3.9/3.10 (pip install tomli)
    import tomli as tomllib

AGRUPACIONES = ("capa", "variable", "grupo", "unico")
RESOLUCIONES = ("auto", "0p25", "0p50", "1p00")
_OBLIGATORIA = object()


class ErrorConfiguracion(ValueError):
    """Configuración ausente o inválida."""


@dataclass(frozen=True)
class Entrada:
    carpeta_fnnn: Path
    resolucion: str
    eliminar_fnnn: bool = True


@dataclass(frozen=True)
class Salida:
    carpeta_salida: Path
    prefijo: str
    grupos: tuple[str, ...]
    conservar_ciclos: int
    agrupacion: str


@dataclass(frozen=True)
class Netcdf:
    compresion: int
    shuffle: bool
    cifras_significativas: int
    archivos_simultaneos: int


@dataclass(frozen=True)
class Proceso:
    procesos: int


@dataclass(frozen=True)
class Config:
    entrada: Entrada
    salida: Salida
    netcdf: Netcdf
    proceso: Proceso


def _leer(seccion: dict, nombre: str, clave: str, tipo, defecto=_OBLIGATORIA):
    if clave not in seccion:
        if defecto is _OBLIGATORIA:
            raise ErrorConfiguracion(f"Falta la clave '{clave}' en [{nombre}]")
        return defecto
    valor = seccion[clave]
    if not isinstance(valor, tipo) or (tipo is not bool and isinstance(valor, bool)):
        raise ErrorConfiguracion(f"[{nombre}] {clave} debe ser {tipo.__name__}, no {type(valor).__name__}")
    return valor


def _seccion(datos: dict, nombre: str) -> dict:
    seccion = datos.get(nombre)
    if not isinstance(seccion, dict):
        raise ErrorConfiguracion(f"Falta la sección [{nombre}]")
    return seccion


def _ruta(texto: str, raiz: Path) -> Path:
    ruta = Path(texto)
    return (ruta if ruta.is_absolute() else raiz / ruta).resolve()


def cargar_configuracion(
    ruta_toml: Path,
    raiz_proyecto: Path,
    agrupacion: str | None = None,
    grupos: list[str] | None = None,
    procesos: int | None = None,
    compresion: int | None = None,
    eliminar_fnnn: bool | None = None,
) -> Config:
    """Lee y valida el TOML. Los argumentos opcionales sustituyen a los del archivo."""
    try:
        with Path(ruta_toml).open("rb") as archivo:
            datos = tomllib.load(archivo)
    except OSError as exc:
        raise ErrorConfiguracion(f"No se pudo leer {ruta_toml}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ErrorConfiguracion(f"TOML inválido en {ruta_toml}: {exc}") from exc

    e, s = _seccion(datos, "entrada"), _seccion(datos, "salida")
    n, p = _seccion(datos, "netcdf"), _seccion(datos, "proceso")
    lista_grupos = grupos if grupos else _leer(s, "salida", "grupos", list)
    if not lista_grupos or not all(isinstance(g, str) and g for g in lista_grupos):
        raise ErrorConfiguracion("[salida] grupos debe ser una lista de textos no vacía")

    cfg = Config(
        entrada=Entrada(
            carpeta_fnnn=_ruta(_leer(e, "entrada", "carpeta_fnnn", str), raiz_proyecto),
            resolucion=_leer(e, "entrada", "resolucion", str, "auto"),
            eliminar_fnnn=(eliminar_fnnn if eliminar_fnnn is not None
                           else _leer(e, "entrada", "eliminar_fnnn", bool, True)),
        ),
        salida=Salida(
            carpeta_salida=_ruta(_leer(s, "salida", "carpeta_salida", str), raiz_proyecto),
            prefijo=_leer(s, "salida", "prefijo", str, "Y0QA1Map"),
            grupos=tuple(lista_grupos),
            conservar_ciclos=_leer(s, "salida", "conservar_ciclos", int, 12),
            agrupacion=agrupacion or _leer(s, "salida", "agrupacion", str, "capa"),
        ),
        netcdf=Netcdf(
            compresion=compresion if compresion is not None else _leer(n, "netcdf", "compresion", int, 1),
            shuffle=_leer(n, "netcdf", "shuffle", bool, True),
            cifras_significativas=_leer(n, "netcdf", "cifras_significativas", int, 0),
            archivos_simultaneos=_leer(n, "netcdf", "archivos_simultaneos", int, 64),
        ),
        proceso=Proceso(
            procesos=procesos if procesos is not None else _leer(p, "proceso", "procesos", int, 0),
        ),
    )
    _validar(cfg)
    return cfg


def _validar(cfg: Config) -> None:
    if cfg.salida.agrupacion not in AGRUPACIONES:
        raise ErrorConfiguracion(f"agrupacion debe ser una de: {', '.join(AGRUPACIONES)}")
    if cfg.entrada.resolucion not in RESOLUCIONES:
        raise ErrorConfiguracion(f"resolucion debe ser una de: {', '.join(RESOLUCIONES)}")
    if not cfg.salida.prefijo.replace("_", "").isalnum():
        raise ErrorConfiguracion("prefijo solo admite letras, números y '_'")
    if cfg.salida.conservar_ciclos < 1:
        raise ErrorConfiguracion("conservar_ciclos debe ser >= 1")
    if not 0 <= cfg.netcdf.compresion <= 9:
        raise ErrorConfiguracion("La compresión NetCDF debe estar entre 0 y 9.")
    if not 0 <= cfg.netcdf.cifras_significativas <= 7:
        raise ErrorConfiguracion("cifras_significativas debe estar entre 0 (sin pérdida) y 7")
    if cfg.netcdf.archivos_simultaneos < 1:
        raise ErrorConfiguracion("archivos_simultaneos debe ser >= 1")
    if cfg.proceso.procesos < 0:
        raise ErrorConfiguracion("procesos no puede ser negativo (0 = automático)")


def procesos_efectivos(cfg: Config) -> int:
    return cfg.proceso.procesos or os.cpu_count() or 1
