"""Definición declarativa de las variables meteorológicas del visor.

Todo lo que cambia de una variable a otra (nombre en el selector, etiqueta del histórico,
unidades, cómo se busca en el NetCDF, cómo se resume un período) vive aquí. El resto del
código consulta ``VARIABLES_METEO`` en vez de repetir diccionarios.

Convención de unidades de almacenamiento (las del histórico):
    gust km/h · tp mm · gh_iso0 m · cape J/kg · tmax/tmin °C · gh_ceiling ft · vis m
"""
from __future__ import annotations

from dataclasses import dataclass

FACTOR_PIES = 3.280839895          # metros -> pies
KELVIN_A_CELSIUS = -273.15
FACTORES_VIENTO = {"km/h": 3.6, "kt": 1.94384449244, "m/s": 1.0}   # desde m/s
UNIDADES_VIENTO = tuple(FACTORES_VIENTO)
CICLOS_VALIDOS = ("00", "06", "12", "18")
HORAS_CIERRE = tuple(f"{hora:02d}" for hora in range(0, 24, 3))


@dataclass(frozen=True)
class VariableMeteo:
    clave: str
    nombre_selector: str            # texto que ve el usuario en el selector de variable
    etiqueta_historico: str         # valor de la columna "Variable" del histórico
    unidad_historico: str           # unidad en que se guarda (y se calcula)
    factor_nc: float                # NetCDF -> unidad del histórico: valor * factor + desplazamiento
    desplazamiento_nc: float
    prefijos_nc: tuple[str, ...]    # prefijos del nombre de la variable dentro del NetCDF
    shortname_nc: str               # GRIB_shortName equivalente
    patrones_archivo: tuple[str, ...]   # glob del archivo .nc, en orden de preferencia
    periodo: str                    # "max" | "min" | "rango" (min y max) | "acumulado"
    unidades: tuple[str, ...]       # unidades que ofrece el selector
    unidad_defecto: str
    archivo_rangos: str | None      # JSON con la paleta de colores (None = sin paleta)
    descripcion_serie: str          # texto bajo el gráfico de la serie temporal
    titulo_leyenda: str = ""
    entero: bool = True             # True: los valores se muestran como enteros

    @property
    def agrega_minimo_por_area(self) -> bool:
        """Para el resumen por área se toma el mínimo de los puntos (si no, el máximo)."""
        return self.periodo == "min"


_LISTA = (
    VariableMeteo(
        "gust", "Racha de viento", "Racha de viento", "km/h", 3.6, 0.0, ("gust",), "gust",
        ("*gust*.nc",), "max", UNIDADES_VIENTO, "km/h", "rangos_viento.json",
        "Rachas en todos los horarios de pronóstico disponibles.", "Rachas de viento"),
    VariableMeteo(
        "tp", "Precipitación total (msg597 / tp)", "Precipitación total", "mm", 1.0, 0.0, ("tp_", "tp"), "tp",
        # El número de mensaje GRIB puede cambiar según la edición del ciclo; tp_sfc es el
        # nombre NetCDF estable de la precipitación total.
        ("*tp_sfc*msg597*.nc", "*tp_sfc*.nc"), "acumulado", ("mm",), "mm", "rangos_precipitacion.json",
        "Precipitación acumulada desde el inicio del ciclo, en todos los horarios disponibles."),
    VariableMeteo(
        "gh_iso0", "Isoterma 0 (gh_iso0)", "Isoterma 0", "m", 1.0, 0.0, ("gh_iso0",), "gh_iso0",
        ("*gh_iso0*msg416*.nc", "*gh_iso0*.nc"), "rango", ("m",), "m", None,
        "Altura de la isoterma 0 en todos los horarios de pronóstico disponibles."),
    VariableMeteo(
        "cape", "CAPE máximo", "CAPE", "J/kg", 1.0, 0.0, ("cape",), "cape",
        ("*cape_sfc*.nc",), "max", ("J/kg",), "J/kg", "rangos_cape.json",
        "CAPE en J/kg, máximo del período.", "CAPE máximo · J/kg"),
    VariableMeteo(
        "tmax", "Temperatura máxima (tmax)", "Temperatura máxima", "°C", 1.0, KELVIN_A_CELSIUS,
        ("tmax_",), "tmax", ("*tmax_2m*.nc",), "max", ("°C",), "°C", "rangos_temperatura.json",
        "Temperatura máxima del período, convertida de K a °C.", "Temperatura máxima · °C"),
    VariableMeteo(
        "tmin", "Temperatura mínima (tmin)", "Temperatura mínima", "°C", 1.0, KELVIN_A_CELSIUS,
        ("tmin_",), "tmin", ("*tmin_2m*.nc",), "min", ("°C",), "°C", "rangos_temperatura.json",
        "Temperatura mínima del período, convertida de K a °C.", "Temperatura mínima · °C"),
    VariableMeteo(
        "gh_ceiling", "Base de nubes (ceiling)", "Base de nubes", "ft", FACTOR_PIES, 0.0,
        ("gh_ceiling",), "gh", ("*gh_ceiling*.nc",), "min", ("m", "ft"), "ft", "rangos_base_nubes.json",
        "Menor altura de base de nubes durante el período.", "Base de nubes"),
    VariableMeteo(
        "vis", "Visibilidad", "Visibilidad", "m", 1.0, 0.0, ("vis_",), "vis",
        ("*vis_sfc*.nc",), "min", ("m",), "m", "rangos_visibilidad.json",
        "Menor visibilidad durante el período.", "Visibilidad · m"),
)

VARIABLES_METEO: dict[str, VariableMeteo] = {v.clave: v for v in _LISTA}
# Selector de la interfaz: texto visible -> clave
VARIABLES: dict[str, str] = {v.nombre_selector: v.clave for v in _LISTA}


def a_unidad_visual(valor, clave: str, unidad: str):
    """Pasa un valor (o arreglo) de la unidad de almacenamiento a la unidad elegida."""
    if clave == "gust":
        return valor * (FACTORES_VIENTO[unidad] / FACTORES_VIENTO["km/h"])
    if clave == "gh_ceiling" and unidad == "m":
        return valor / FACTOR_PIES
    return valor
