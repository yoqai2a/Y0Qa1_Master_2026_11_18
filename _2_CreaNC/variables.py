"""Lectura de __Variables_NC.toml: qué campos GRIB se escriben y cómo se llaman.

Cada [[campo]] describe una variable física (shortName + tipo de nivel) y la
lista de niveles que se quiere. Se identifica por NOMBRE, no por número de
mensaje: sigue funcionando si cambia el conjunto descargado o el orden de los
mensajes en el GRIB.
"""
from __future__ import annotations

import math
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - Python 3.9/3.10 (pip install tomli)
    import tomli as tomllib

TIPOS_INTERVALO = ("desde_inicio",)
POLITICAS_DUPLICADOS = ("ultimo", "primero", "error")

# Etiqueta del nivel dentro del nombre de la variable NetCDF.
_NIVEL_NUMERICO = {  # tipo -> (prefijo, sufijo)
    "isobaricInhPa": ("", "hPa"),
    "isobaricInPa": ("", "Pa"),
    "heightAboveGround": ("", "m"),
    "heightAboveSea": ("", "masl"),
    "hybrid": ("hyb", ""),
    "sigma": ("sigma", ""),
}
_ABREVIATURA = {
    "surface": "sfc", "meanSea": "msl", "atmosphere": "atm",
    "atmosphereSingleLayer": "atmcol", "cloudCeiling": "ceiling",
    "tropopause": "trop", "maxWind": "maxwind", "isothermZero": "iso0",
    "highestTroposphericFreezing": "frzlvl", "planetaryBoundaryLayer": "pbl",
    "heightAboveGroundLayer": "agl", "depthBelowLandLayer": "soil",
    "pressureFromGroundLayer": "pfg",
}


class ErrorVariables(ValueError):
    """__Variables_NC.toml ausente o inválido."""


@dataclass(frozen=True)
class Capa:
    """Un campo en un nivel = una variable del NetCDF."""
    nombre: str
    grupo: str
    short_name: str
    long_name: str
    unidades: str
    tipo_nivel: str
    nivel: float
    top: float | None
    bottom: float | None
    step_type: str
    desde_inicio: bool = False
    ocurrencia: int | None = None
    parametro: tuple[int, int, int] | None = None
    duplicados: str = "ultimo"

    @property
    def clave(self) -> tuple:
        return clave_primaria(self.short_name, self.tipo_nivel, self.nivel, self.step_type)


def clave_primaria(short_name, tipo_nivel, nivel, step_type) -> tuple:
    """Clave de búsqueda rápida (se compara igual en el catálogo y en el GRIB)."""
    return (str(short_name), str(tipo_nivel), round(float(nivel), 6), str(step_type))


# ----------------------------------------------------------------------------
# Nombres de variable
# ----------------------------------------------------------------------------
def limpiar(texto: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", str(texto)).strip("_") or "x"


def _num(valor: float) -> str:
    v = float(valor)
    texto = str(int(v)) if v.is_integer() else f"{v:g}"
    return texto.replace(".", "p").replace("-", "m")


def etiqueta_nivel(tipo: str, nivel: float, top: float | None, bottom: float | None) -> str:
    if top is not None and bottom is not None:      # capa entre dos superficies
        a, b = sorted((float(top), float(bottom)))
        return f"{_ABREVIATURA.get(tipo, limpiar(tipo))}{_num(a)}_{_num(b)}"
    if tipo in _NIVEL_NUMERICO:
        pre, suf = _NIVEL_NUMERICO[tipo]
        return f"{pre}{_num(nivel)}{suf}"
    base = _ABREVIATURA.get(tipo, limpiar(tipo))
    return base if float(nivel) == 0 else f"{base}_{_num(nivel)}"


def _asignar_nombres(pendientes: list[dict]) -> list[str]:
    """Nombres únicos y legibles: t_850hPa, 2t_2m, prate_sfc, prate_sfc_avg..."""
    base = [
        f"{limpiar(p['short_name'])}_{etiqueta_nivel(p['tipo_nivel'], p['nivel'], p['top'], p['bottom'])}"
        + (f"_{limpiar(p['sufijo'])}" if p["sufijo"] else "")
        for p in pendientes
    ]
    cuenta = Counter(base)
    nombres = []
    for p, b in zip(pendientes, base):
        # Ante una colisión el campo 'instant' conserva el nombre simple.
        if cuenta[b] > 1 and p["step_type"] != "instant":
            b = f"{b}_{limpiar(p['step_type'])}"
        nombres.append(b)
    repetidos = [n for n, c in Counter(nombres).items() if c > 1]
    if repetidos:
        raise ErrorVariables(
            "Nombres de variable repetidos: " + ", ".join(sorted(repetidos)[:5])
            + ". Añade 'sufijo' a uno de los [[campo]] para distinguirlos."
        )
    return nombres


# ----------------------------------------------------------------------------
# Carga del TOML
# ----------------------------------------------------------------------------
def _texto(c: dict, clave: str, donde: str, defecto=None, obligatorio=False) -> str | None:
    if clave not in c:
        if obligatorio:
            raise ErrorVariables(f"{donde}: falta '{clave}'")
        return defecto
    if not isinstance(c[clave], str) or not c[clave]:
        raise ErrorVariables(f"{donde}: '{clave}' debe ser un texto no vacío")
    return c[clave]


def _numero(valor, donde: str, clave: str) -> float:
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ErrorVariables(f"{donde}: '{clave}' debe ser un número")
    return float(valor)


def _parametro(valor, donde: str) -> tuple[int, int, int] | None:
    if valor is None:
        return None
    partes = valor.split(".") if isinstance(valor, str) else valor
    try:
        d, c, n = (int(x) for x in partes)
    except (TypeError, ValueError) as exc:
        raise ErrorVariables(f"{donde}: 'parametro' debe ser \"disciplina.categoria.numero\"") from exc
    return d, c, n


def _niveles(c: dict, donde: str) -> list[tuple[float, float | None, float | None]]:
    niveles = c.get("niveles")
    if not isinstance(niveles, list) or not niveles:
        raise ErrorVariables(f"{donde}: 'niveles' debe ser una lista no vacía")
    salida = []
    for item in niveles:
        if isinstance(item, dict):
            if "level" not in item:
                raise ErrorVariables(f"{donde}: cada nivel con tabla necesita 'level'")
            top = item.get("topLevel")
            bottom = item.get("bottomLevel")
            salida.append((
                _numero(item["level"], donde, "level"),
                None if top is None else _numero(top, donde, "topLevel"),
                None if bottom is None else _numero(bottom, donde, "bottomLevel"),
            ))
        else:
            salida.append((_numero(item, donde, "niveles"), None, None))
    return salida


def cargar_variables(ruta: Path) -> list[Capa]:
    try:
        with Path(ruta).open("rb") as archivo:
            datos = tomllib.load(archivo)
    except OSError as exc:
        raise ErrorVariables(f"No se pudo leer {ruta}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ErrorVariables(f"TOML inválido en {ruta}: {exc}") from exc
    campos = datos.get("campo")
    if not isinstance(campos, list) or not campos:
        raise ErrorVariables(f"{ruta} no define ningún [[campo]]")

    pendientes: list[dict] = []
    for n, c in enumerate(campos, 1):
        donde = f"[[campo]] nº {n} ({c.get('shortName', '?')})"
        if not c.get("activo", True):
            continue
        intervalo = c.get("intervalo")
        if intervalo is not None and intervalo not in TIPOS_INTERVALO:
            raise ErrorVariables(f"{donde}: 'intervalo' debe ser {TIPOS_INTERVALO}")
        duplicados = c.get("duplicados", "ultimo")
        if duplicados not in POLITICAS_DUPLICADOS:
            raise ErrorVariables(f"{donde}: 'duplicados' debe ser una de {POLITICAS_DUPLICADOS}")
        ocurrencia = c.get("ocurrencia")
        if ocurrencia is not None and (isinstance(ocurrencia, bool) or not isinstance(ocurrencia, int) or ocurrencia < 1):
            raise ErrorVariables(f"{donde}: 'ocurrencia' debe ser un entero >= 1")
        for nivel, top, bottom in _niveles(c, donde):
            pendientes.append(dict(
                grupo=_texto(c, "grupo", donde, "Main"),
                short_name=_texto(c, "shortName", donde, obligatorio=True),
                long_name=_texto(c, "nombre", donde, "") or "",
                unidades=_texto(c, "unidades", donde, "") or "",
                tipo_nivel=_texto(c, "tipoNivel", donde, obligatorio=True),
                nivel=nivel, top=top, bottom=bottom,
                step_type=_texto(c, "stepType", donde, "instant"),
                desde_inicio=intervalo == "desde_inicio",
                ocurrencia=ocurrencia, duplicados=duplicados,
                parametro=_parametro(c.get("parametro"), donde),
                sufijo=_texto(c, "sufijo", donde, ""),
            ))
    if not pendientes:
        raise ErrorVariables(f"{ruta}: todos los [[campo]] están desactivados")

    nombres = _asignar_nombres(pendientes)
    capas = []
    for nombre, p in zip(nombres, pendientes):
        p = dict(p)
        p.pop("sufijo")
        capas.append(Capa(nombre=nombre, **p))
    return capas


def indexar(capas: list[Capa]) -> dict[tuple, list[Capa]]:
    """clave primaria -> capas candidatas (varias si se distinguen por top/bottom/filtros)."""
    indice: dict[tuple, list[Capa]] = {}
    for capa in capas:
        indice.setdefault(capa.clave, []).append(capa)
    return indice


def mismo_nivel(a: float | None, b: float | None) -> bool:
    return a is not None and b is not None and math.isclose(float(a), float(b), rel_tol=0, abs_tol=1e-8)
