"""Carga y validación de __Configuracion_Fnnn.toml.

Devuelve dataclasses inmutables en lugar de diccionarios: un error de tipeo en
una clave falla al cargar, no a mitad de la descarga.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, replace
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - Python 3.9/3.10 (pip install tomli)
    import tomli as tomllib

RESOLUCIONES = ("0p25", "0p50", "1p00")
_OBLIGATORIA = object()


class ErrorConfiguracion(ValueError):
    """Configuración ausente o inválida."""


@dataclass(frozen=True)
class Conjunto:
    nombre: str
    todas_variables: bool = False
    todos_niveles: bool = False
    variables: tuple[str, ...] = ()
    niveles: tuple[str, ...] = ()


@dataclass(frozen=True)
class Modelo:
    url_base: str
    url_prod: str
    resolucion: str
    conjunto: str
    parametros_extra: tuple[str, ...]
    paso_fino_horas: int
    dias_horarios: int
    dias_maximos: int
    hora_cierre_utc: int
    area: str


@dataclass(frozen=True)
class Area:
    nombre: str
    norte: float
    sur: float
    oeste: float
    este: float


@dataclass(frozen=True)
class Ciclos:
    retraso_publicacion_horas: float
    exigir_completo: bool


@dataclass(frozen=True)
class Descarga:
    carpeta_salida: Path
    conexiones: int
    reintentos: int
    espera_reintento_s: float
    tamano_minimo_bytes: int
    retencion_horas: float
    timeout_conexion_s: float
    timeout_lectura_s: float


@dataclass(frozen=True)
class Flujo:
    crear_nc: bool = False


@dataclass(frozen=True)
class Config:
    modelo: Modelo
    area: Area
    ciclos: Ciclos
    descarga: Descarga
    conjunto: Conjunto  # el conjunto elegido en modelo.conjunto
    conjuntos_disponibles: tuple[str, ...] = ()
    areas_disponibles: tuple[str, ...] = ()
    flujo: Flujo = Flujo()


def _leer(seccion: dict, nombre_seccion: str, clave: str, tipo, defecto=_OBLIGATORIA):
    if clave not in seccion:
        if defecto is _OBLIGATORIA:
            raise ErrorConfiguracion(f"Falta la clave '{clave}' en [{nombre_seccion}]")
        return defecto
    valor = seccion[clave]
    if tipo is float and isinstance(valor, int) and not isinstance(valor, bool):
        valor = float(valor)
    if not isinstance(valor, tipo) or (tipo is not bool and isinstance(valor, bool)):
        raise ErrorConfiguracion(
            f"[{nombre_seccion}] {clave} debe ser {tipo.__name__}, no {type(valor).__name__}"
        )
    return valor


def _seccion(datos: dict, nombre: str) -> dict:
    seccion = datos.get(nombre)
    if not isinstance(seccion, dict):
        raise ErrorConfiguracion(f"Falta la sección [{nombre}]")
    return seccion


def _lista_texto(seccion: dict, nombre_seccion: str, clave: str) -> tuple[str, ...]:
    valor = _leer(seccion, nombre_seccion, clave, list, [])
    if not all(isinstance(x, str) and x for x in valor):
        raise ErrorConfiguracion(f"[{nombre_seccion}] {clave} debe ser una lista de textos")
    return tuple(valor)


def _leer_conjuntos(datos: dict) -> dict[str, Conjunto]:
    conjuntos = {}
    for nombre, c in _seccion(datos, "conjuntos").items():
        if not isinstance(c, dict):
            raise ErrorConfiguracion(f"[conjuntos.{nombre}] debe ser una sección")
        seccion = f"conjuntos.{nombre}"
        conjunto = Conjunto(
            nombre=nombre,
            todas_variables=_leer(c, seccion, "todas_variables", bool, False),
            todos_niveles=_leer(c, seccion, "todos_niveles", bool, False),
            variables=_lista_texto(c, seccion, "variables"),
            niveles=_lista_texto(c, seccion, "niveles"),
        )
        if not (conjunto.todas_variables or conjunto.variables):
            raise ErrorConfiguracion(f"[{seccion}] no define variables ni todas_variables")
        if not (conjunto.todos_niveles or conjunto.niveles):
            raise ErrorConfiguracion(f"[{seccion}] no define niveles ni todos_niveles")
        conjuntos[nombre] = conjunto
    return conjuntos


def _leer_areas(datos: dict) -> dict[str, Area]:
    areas = {}
    for nombre, a in _seccion(datos, "areas").items():
        if not isinstance(a, dict):
            raise ErrorConfiguracion(f"[areas.{nombre}] debe ser una sección")
        seccion = f"areas.{nombre}"
        areas[nombre] = Area(
            nombre,
            *(_leer(a, seccion, k, float) for k in ("norte", "sur", "oeste", "este")),
        )
    return areas


def _elegir(nombre: str, disponibles, tipo: str) -> str:
    """Busca `nombre` sin distinguir mayúsculas; error claro si no existe."""
    elegido = next((n for n in disponibles if n.casefold() == nombre.casefold()), None)
    if elegido is None:
        raise ErrorConfiguracion(f"{tipo} '{nombre}' no existe; usa uno de: {', '.join(disponibles)}")
    return elegido


def cargar_configuracion(
    ruta_toml: Path,
    raiz_proyecto: Path,
    conjunto: str | None = None,
    area: str | None = None,
    crear_nc: bool | None = None,
) -> Config:
    """Lee y valida el TOML.

    `conjunto` y `area` (opcionales) sustituyen a modelo.conjunto y modelo.area.

    Las rutas relativas de descarga.carpeta_salida se resuelven contra
    `raiz_proyecto`, no contra la carpeta desde la que se ejecuta el script.
    """
    try:
        with Path(ruta_toml).open("rb") as archivo:
            datos = tomllib.load(archivo)
    except OSError as exc:
        raise ErrorConfiguracion(f"No se pudo leer {ruta_toml}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ErrorConfiguracion(f"TOML inválido en {ruta_toml}: {exc}") from exc

    m = _seccion(datos, "modelo")
    c, d = _seccion(datos, "ciclos"), _seccion(datos, "descarga")
    conjuntos = _leer_conjuntos(datos)
    areas = _leer_areas(datos)

    modelo = Modelo(
        url_base=_leer(m, "modelo", "url_base", str).rstrip("/"),
        url_prod=_leer(m, "modelo", "url_prod", str).rstrip("/"),
        resolucion=_leer(m, "modelo", "resolucion", str),
        conjunto=conjunto or _leer(m, "modelo", "conjunto", str),
        parametros_extra=_lista_texto(m, "modelo", "parametros_extra"),
        paso_fino_horas=_leer(m, "modelo", "paso_fino_horas", int),
        dias_horarios=_leer(m, "modelo", "dias_horarios", int),
        dias_maximos=_leer(m, "modelo", "dias_maximos", int),
        hora_cierre_utc=_leer(m, "modelo", "hora_cierre_utc", int),
        area=area or _leer(m, "modelo", "area", str),
    )
    ciclos = Ciclos(
        retraso_publicacion_horas=_leer(c, "ciclos", "retraso_publicacion_horas", float),
        exigir_completo=_leer(c, "ciclos", "exigir_completo", bool, False),
    )
    carpeta = Path(_leer(d, "descarga", "carpeta_salida", str))
    if not carpeta.is_absolute():
        carpeta = raiz_proyecto / carpeta
    descarga = Descarga(
        carpeta_salida=carpeta.resolve(),
        conexiones=_leer(d, "descarga", "conexiones", int),
        reintentos=_leer(d, "descarga", "reintentos", int),
        espera_reintento_s=_leer(d, "descarga", "espera_reintento_s", float),
        tamano_minimo_bytes=_leer(d, "descarga", "tamano_minimo_bytes", int),
        retencion_horas=_leer(d, "descarga", "retencion_horas", float),
        timeout_conexion_s=_leer(d, "descarga", "timeout_conexion_s", float, 20.0),
        timeout_lectura_s=_leer(d, "descarga", "timeout_lectura_s", float, 180.0),
    )

    elegido = _elegir(modelo.conjunto, conjuntos, "Conjunto")
    area_elegida = _elegir(modelo.area, areas, "Área")
    modelo = replace(modelo, conjunto=elegido, area=area_elegida)

    f = datos.get("flujo", {})
    if not isinstance(f, dict):
        raise ErrorConfiguracion("[flujo] debe ser una sección")
    flujo = Flujo(crear_nc=crear_nc if crear_nc is not None else _leer(f, "flujo", "crear_nc", bool, False))

    cfg = Config(modelo, areas[area_elegida], ciclos, descarga, conjuntos[elegido],
                 tuple(conjuntos), tuple(areas), flujo)
    _validar(cfg)
    return cfg


def _validar(cfg: Config) -> None:
    """Mismas reglas que la versión monolítica, más comprobaciones de rango."""
    m, a, d = cfg.modelo, cfg.area, cfg.descarga
    if m.resolucion not in RESOLUCIONES:
        raise ErrorConfiguracion(f"resolucion debe ser una de: {', '.join(RESOLUCIONES)}")
    if m.hora_cierre_utc != 3:
        raise ErrorConfiguracion("hora_cierre_utc debe ser 3 (00:00 local UTC-3)")
    if not 1 <= m.dias_horarios <= m.dias_maximos <= 7:
        raise ErrorConfiguracion("Se requiere 1 <= dias_horarios <= dias_maximos <= 7")
    if m.paso_fino_horas != 1:
        raise ErrorConfiguracion("paso_fino_horas debe ser 1")
    if d.conexiones < 1 or d.reintentos < 1:
        raise ErrorConfiguracion("conexiones y reintentos deben ser mayores que cero")
    if d.retencion_horas <= 0:
        raise ErrorConfiguracion("retencion_horas debe ser mayor que cero")
    if d.tamano_minimo_bytes < 0 or d.espera_reintento_s < 0:
        raise ErrorConfiguracion("tamano_minimo_bytes y espera_reintento_s no pueden ser negativos")
    if d.timeout_conexion_s <= 0 or d.timeout_lectura_s <= 0:
        raise ErrorConfiguracion("Los timeouts deben ser mayores que cero")
    if cfg.ciclos.retraso_publicacion_horas < 0:
        raise ErrorConfiguracion("retraso_publicacion_horas no puede ser negativo")
    if not (-90 <= a.sur < a.norte <= 90):
        raise ErrorConfiguracion(f"[areas.{a.nombre}] norte/sur inválidos (sur < norte)")
    if not (-180 <= a.oeste < a.este <= 180):
        raise ErrorConfiguracion(f"[areas.{a.nombre}] oeste/este inválidos (oeste < este)")
