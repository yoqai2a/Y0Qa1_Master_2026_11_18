"""Lectura y validación de la configuración de la pestaña Corte temporal.

Los archivos están en ``configuracion/``: capas_nc.json, variables.json, puntos.json y
almacenamiento.json. Un error en ellos se informa con un mensaje claro (ErrorConfigCorte).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

CARPETA_CONFIG = Path(__file__).resolve().parent / "configuracion"
ARCHIVO_CAPAS = CARPETA_CONFIG / "capas_nc.json"
ARCHIVO_VARIABLES = CARPETA_CONFIG / "variables.json"
ARCHIVO_PUNTOS = CARPETA_CONFIG / "puntos.json"
ARCHIVO_ALMACENAMIENTO = CARPETA_CONFIG / "almacenamiento.json"

_NOMBRE_CAPA = re.compile(r"([A-Za-z0-9]+)_(\d+)hPa")
_EXTENSIONES = {"neither", "both", "min", "max"}
ESCALAS_VERTICALES = ("lineal", "logaritmica")


class ErrorConfigCorte(ValueError):
    """Configuración de Corte temporal ausente o inválida."""


@dataclass(frozen=True)
class CapaCfg:
    prefijo: str
    nombre: str
    unidad: str            # unidad en que se guardan los valores
    factor: float          # valor del NetCDF -> unidad guardada: valor * factor + desplazamiento
    desplazamiento: float


@dataclass(frozen=True)
class UnidadVista:
    nombre: str
    factor: float          # unidad guardada -> unidad mostrada
    desplazamiento: float
    minimo: float
    maximo: float
    paso: float


@dataclass(frozen=True)
class Contorno:
    valor: float
    etiqueta: str
    color: str
    ancho: float


@dataclass(frozen=True)
class Vista:
    nombre: str
    campo: str             # prefijo de capa (t, r, u, v...) o "rapidez"
    paleta: str
    extension: str
    unidades: dict[str, UnidadVista]
    contornos: tuple[Contorno, ...]
    barbas: bool
    centro: float | None = None     # valor que cae en el centro de la paleta (p. ej. 0 °C)

    @property
    def capas_necesarias(self) -> tuple[str, ...]:
        return ("u", "v") if self.campo == "rapidez" else (self.campo,)


@dataclass(frozen=True)
class VariableCorte:
    nombre: str
    vistas: dict[str, Vista]


@dataclass(frozen=True)
class ConfigCorte:
    capas: dict[str, CapaCfg]
    variables: dict[str, VariableCorte]
    niveles_por_capa: dict[str, tuple[int, ...]]     # {"t": (200, 250, ... 1000)}
    escala_vertical_defecto: str
    publicar_nc_en_git: bool = False
    puntos_ruta: Path = field(default=ARCHIVO_PUNTOS)

    @property
    def todas_las_capas(self) -> list[tuple[str, int]]:
        return [(pre, n) for pre, niveles in self.niveles_por_capa.items() for n in niveles]


def _leer_json(ruta: Path) -> dict:
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise ErrorConfigCorte(f"Falta el archivo de configuración {ruta}.") from exc
    except (OSError, ValueError) as exc:
        raise ErrorConfigCorte(f"No se pudo leer {ruta.name}: {exc}") from exc
    if not isinstance(datos, dict):
        raise ErrorConfigCorte(f"{ruta.name} debe contener un objeto JSON.")
    return datos


def _numero(valor, donde: str) -> float:
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ErrorConfigCorte(f"{donde} debe ser un número.")
    return float(valor)


def niveles_desde_capas(ruta: Path = ARCHIVO_CAPAS) -> dict[str, tuple[int, ...]]:
    """{prefijo: niveles hPa} de las capas activas en capas_nc.json (de mayor a menor presión)."""
    archivos = _leer_json(ruta).get("archivos")
    if not isinstance(archivos, dict):
        raise ErrorConfigCorte(f"{ruta.name}: falta el objeto 'archivos'.")
    niveles: dict[str, set[int]] = {}
    for nombre, activo in archivos.items():
        if activo is not True:
            continue
        m = _NOMBRE_CAPA.fullmatch(nombre)
        if not m:
            raise ErrorConfigCorte(f"{ruta.name}: '{nombre}' no tiene el formato variable_nivelhPa (p. ej. t_850hPa).")
        niveles.setdefault(m.group(1), set()).add(int(m.group(2)))
    return {pre: tuple(sorted(lista, reverse=True)) for pre, lista in niveles.items()}


def _nombres_de_paletas() -> frozenset[str] | None:
    """Nombres de paletas de matplotlib, o None si no está instalado (p. ej. en GitHub Actions,
    que solo crea los respaldos y no dibuja). En ese caso la paleta se valida al dibujar, en el visor."""
    try:
        from matplotlib import colormaps
    except ImportError:
        return None
    return frozenset(colormaps)


def _vista(nombre: str, datos: dict, capas: dict[str, CapaCfg]) -> Vista:
    donde = f"variables.json › vista '{nombre}'"
    campo = datos.get("campo")
    if campo != "rapidez" and campo not in capas:
        raise ErrorConfigCorte(f"{donde}: campo '{campo}' no existe (use una capa de 'capas' o 'rapidez').")
    if campo == "rapidez" and not {"u", "v"} <= set(capas):
        raise ErrorConfigCorte(f"{donde}: 'rapidez' necesita las capas u y v en 'capas'.")
    paleta = datos.get("paleta", "viridis")
    paletas = _nombres_de_paletas()
    if paletas is not None and paleta not in paletas:
        raise ErrorConfigCorte(f"{donde}: la paleta '{paleta}' no existe en matplotlib.")
    extension = datos.get("extension", "both")
    if extension not in _EXTENSIONES:
        raise ErrorConfigCorte(f"{donde}: 'extension' debe ser una de {sorted(_EXTENSIONES)}.")
    unidades: dict[str, UnidadVista] = {}
    for unidad, u in (datos.get("unidades") or {}).items():
        minimo, maximo, paso = (_numero(u.get(k), f"{donde} › {unidad} › {k}") for k in ("min", "max", "paso"))
        if not minimo < maximo or paso <= 0:
            raise ErrorConfigCorte(f"{donde} › {unidad}: se requiere min < max y paso > 0.")
        unidades[unidad] = UnidadVista(
            unidad, _numero(u.get("factor", 1.0), f"{donde} › {unidad} › factor"),
            _numero(u.get("desplazamiento", 0.0), f"{donde} › {unidad} › desplazamiento"), minimo, maximo, paso)
    if not unidades:
        raise ErrorConfigCorte(f"{donde}: define al menos una unidad en 'unidades'.")
    contornos = tuple(
        Contorno(_numero(c.get("valor"), f"{donde} › contorno › valor"), str(c.get("etiqueta", c.get("valor"))),
                 str(c.get("color", "black")), _numero(c.get("ancho", 1.2), f"{donde} › contorno › ancho"))
        for c in datos.get("contornos_resaltados", []))
    centro = datos.get("centro")
    if centro is not None:
        centro = _numero(centro, f"{donde} › centro")
    return Vista(nombre, campo, paleta, extension, unidades, contornos, bool(datos.get("barbas", False)), centro)


@lru_cache(maxsize=4)
def _cargar(firma: tuple) -> ConfigCorte:
    del firma   # solo sirve de clave de caché: si algún archivo cambia, se vuelve a leer
    datos = _leer_json(ARCHIVO_VARIABLES)
    capas: dict[str, CapaCfg] = {}
    for prefijo, c in (datos.get("capas") or {}).items():
        capas[prefijo] = CapaCfg(prefijo, str(c.get("nombre", prefijo)), str(c.get("unidad", "")),
                                 _numero(c.get("factor", 1.0), f"capas › {prefijo} › factor"),
                                 _numero(c.get("desplazamiento", 0.0), f"capas › {prefijo} › desplazamiento"))
    if not capas:
        raise ErrorConfigCorte("variables.json: falta la sección 'capas'.")
    variables: dict[str, VariableCorte] = {}
    for nombre, v in (datos.get("variables") or {}).items():
        vistas = {n: _vista(n, d, capas) for n, d in (v.get("vistas") or {}).items()}
        if not vistas:
            raise ErrorConfigCorte(f"variables.json: la variable '{nombre}' no tiene vistas.")
        variables[nombre] = VariableCorte(nombre, vistas)
    if not variables:
        raise ErrorConfigCorte("variables.json: falta la sección 'variables'.")
    escala = datos.get("escala_vertical_defecto", "lineal")
    if escala not in ESCALAS_VERTICALES:
        raise ErrorConfigCorte(f"variables.json: 'escala_vertical_defecto' debe ser una de {ESCALAS_VERTICALES}.")
    niveles = niveles_desde_capas()
    desconocidas = sorted(set(niveles) - set(capas))
    if desconocidas:
        raise ErrorConfigCorte("capas_nc.json tiene variables que no están en 'capas' de variables.json: "
                               + ", ".join(desconocidas))
    for nombre, var in variables.items():
        for vista in var.vistas.values():
            faltan = [c for c in vista.capas_necesarias if not niveles.get(c)]
            if faltan:
                raise ErrorConfigCorte(f"La vista '{vista.nombre}' ({nombre}) necesita capas {faltan} activas en capas_nc.json.")
    alm = _leer_json(ARCHIVO_ALMACENAMIENTO)
    return ConfigCorte(capas, variables, {p: niveles[p] for p in capas if p in niveles}, escala,
                       bool(alm.get("publicar_nc_en_git", False)))


def cargar_config() -> ConfigCorte:
    """Configuración validada (se relee solo cuando cambia algún archivo de ``configuracion/``)."""
    firma = tuple(ruta.stat().st_mtime_ns if ruta.exists() else 0
                  for ruta in (ARCHIVO_CAPAS, ARCHIVO_VARIABLES, ARCHIVO_ALMACENAMIENTO))
    return _cargar(firma)
