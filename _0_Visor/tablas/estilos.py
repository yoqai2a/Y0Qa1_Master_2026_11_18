"""Paletas de colores, leyendas y estilo de las tablas.

Los rangos de color se leen de los JSON ``rangos_*.json``; cada color se valida al cargarlo
y todo texto que llega a HTML se escapa, de modo que un JSON editado por error no pueda
romper la página ni inyectar código.
"""
from __future__ import annotations

import html
import re

import pandas as pd
import streamlit as st

from .datos import CARPETA_CONFIG, leer_json_cacheado
from .variables import FACTOR_PIES, FACTORES_VIENTO, VARIABLES_METEO

_COLOR_HEX = re.compile(r"#[0-9A-Fa-f]{3,8}")


def _color_css(valor, defecto: str) -> str:
    texto = str(valor or "").strip()
    return texto if _COLOR_HEX.fullmatch(texto) else defecto


def _sanear_rango(rango: dict) -> dict:
    limpio = dict(rango)
    limpio["fondo"] = _color_css(rango.get("fondo"), "#FFFFFF")
    limpio["texto"] = _color_css(rango.get("texto"), "#202938")
    limpio["etiqueta"] = str(rango.get("etiqueta", ""))
    return limpio


def cargar_rangos(tipo_variable: str) -> dict:
    """Paleta de la variable (se vuelve a leer solo si el JSON cambió)."""
    nombre = VARIABLES_METEO[tipo_variable].archivo_rangos
    if nombre is None:
        raise KeyError(f"{tipo_variable} no tiene paleta de colores.")
    ruta = CARPETA_CONFIG / nombre
    datos = leer_json_cacheado(ruta)
    if not isinstance(datos.get("rangos"), list) or not datos["rangos"]:
        raise ValueError(f"El archivo {ruta.name} no contiene rangos válidos.")
    datos["rangos"] = [_sanear_rango(r) for r in datos["rangos"]]
    datos["rangos_por_area"] = {area: [_sanear_rango(r) for r in lista]
                                for area, lista in datos.get("rangos_por_area", {}).items()}
    if "color_sin_paleta" in datos:
        gris = datos["color_sin_paleta"]
        datos["color_sin_paleta"] = {"fondo": _color_css(gris.get("fondo"), "#F2F2F2"),
                                     "texto": _color_css(gris.get("texto"), "#000000")}
    return datos


def color_de(valor, rangos: list[dict]) -> tuple[str, str]:
    """(fondo, texto) del rango al que pertenece el valor, o ('', '') si no hay."""
    if valor is None or pd.isna(valor):
        return "", ""
    valor = float(valor)
    for rango in rangos:
        minimo, maximo = rango.get("minimo"), rango.get("maximo")
        cumple_minimo = minimo is None or (valor >= minimo if rango.get("incluye_minimo", True) else valor > minimo)
        cumple_maximo = maximo is None or (valor <= maximo if rango.get("incluye_maximo", False) else valor < maximo)
        if cumple_minimo and cumple_maximo:
            return rango["fondo"], rango["texto"]
    return "", ""


def escala_de_color(tipo_variable: str, unidad: str) -> float:
    """Factor para comparar el valor mostrado con los umbrales guardados (base de nubes en pies)."""
    return FACTOR_PIES if tipo_variable == "gh_ceiling" and unidad == "m" else 1.0


def tabla_con_colores(filas: list[dict], tipo_variable: str, config: dict | None = None,
                      escala: float = 1.0, area_detalle: str | None = None):
    tabla = pd.DataFrame(filas)
    columnas_valores = list(tabla.columns[1:])
    if tipo_variable == "gh_iso0" or not config:
        return tabla.style.format(precision=0, na_rep="—")

    def estilos(fila):
        resultado = [""] * len(fila)
        area = fila.get("Área", area_detalle)
        if tipo_variable == "tp" and area in config.get("areas_sin_colores", []):
            gris = config.get("color_sin_paleta", {"fondo": "#F2F2F2", "texto": "#000000"})
            for indice, columna in enumerate(fila.index):
                if columna in columnas_valores:
                    resultado[indice] = f"background-color: {gris['fondo']}; color: {gris['texto']}; font-weight: 600"
            return resultado
        rangos = config.get("rangos_por_area", {}).get(area, config["rangos"])
        for indice, columna in enumerate(fila.index):
            if columna not in columnas_valores or pd.isna(fila[columna]):
                continue
            fondo, texto = color_de(float(fila[columna]) * escala, rangos)
            if fondo:
                resultado[indice] = f"background-color: {fondo}; color: {texto}; font-weight: 600"
        return resultado

    return tabla.style.apply(estilos, axis=1).format(precision=0, na_rep="—")


# --------------------------------------------------------------------------- leyendas
def _caja_color(fondo: str, texto: str, contenido: str, margen: int = 5) -> str:
    return (f"<div style='padding:5px 6px;margin-bottom:{margen}px;background:{html.escape(fondo)};"
            f"color:{html.escape(texto)};border:1px solid #cbd5e1;border-radius:4px;text-align:center'>"
            f"{html.escape(contenido)}</div>")


def pintar_leyenda(config: dict, titulo: str) -> None:
    st.markdown(f"**{titulo}**")
    rangos = config["rangos"]
    for columna, rango in zip(st.columns(len(rangos)), rangos):
        with columna:
            st.markdown(_caja_color(rango["fondo"], rango["texto"], rango["etiqueta"]), unsafe_allow_html=True)


def rangos_base_nubes_en_unidad(config: dict, unidad: str) -> dict:
    """Ajusta límites guardados en pies a la unidad de presentación."""
    factor = 1.0 if unidad == "ft" else 1 / FACTOR_PIES
    rangos = []
    for rango in config["rangos"]:
        convertido = dict(rango)
        minimo = None if rango["minimo"] is None else rango["minimo"] * factor
        maximo = None if rango["maximo"] is None else rango["maximo"] * factor
        convertido.update(minimo=minimo, maximo=maximo)
        if minimo is None:
            convertido["etiqueta"] = f"bajo {int(round(maximo))} {unidad}"
        elif maximo is None:
            convertido["etiqueta"] = f"más de {int(round(minimo))} {unidad}"
        else:
            convertido["etiqueta"] = f"{int(round(minimo))} a {int(round(maximo))} {unidad}"
        rangos.append(convertido)
    return {**config, "rangos": rangos}


def rangos_viento_en_unidad(config: dict, unidad: str) -> dict:
    """Convierte los límites almacenados en km/h a la unidad que muestra la tabla."""
    factor = FACTORES_VIENTO[unidad] / FACTORES_VIENTO["km/h"]

    def formato(valor):
        if valor is None:
            return ""
        return str(int(round(valor))) if abs(valor - round(valor)) < 1e-9 else f"{valor:.1f}"

    convertidos = []
    for rango in config["rangos"]:
        minimo = None if rango["minimo"] is None else rango["minimo"] * factor
        maximo = None if rango["maximo"] is None else rango["maximo"] * factor
        if maximo is None:
            etiqueta = f"más de {formato(minimo)} {unidad}"
        elif rango.get("incluye_minimo", True) and (minimo is None or minimo == 0):
            etiqueta = f"{formato(minimo)} a {formato(maximo)} {unidad}"
        else:
            etiqueta = f"más de {formato(minimo)} a {formato(maximo)} {unidad}"
        convertido = dict(rango)
        convertido.update(minimo=minimo, maximo=maximo, etiqueta=etiqueta)
        convertidos.append(convertido)
    return {**config, "rangos": convertidos, "unidad_umbral": unidad}


def config_colores(tipo_variable: str, unidad: str) -> dict | None:
    """Paleta lista para usar en la tabla (None si la variable no tiene colores)."""
    if VARIABLES_METEO[tipo_variable].archivo_rangos is None:
        return None
    config = cargar_rangos(tipo_variable)
    return rangos_viento_en_unidad(config, unidad) if tipo_variable == "gust" else config


def mostrar_leyenda(tipo_variable: str, unidad: str) -> None:
    with st.popover("Leyendas", use_container_width=True):
        if tipo_variable == "gh_iso0":
            st.caption("La isoterma 0 no utiliza paleta de colores.")
        elif tipo_variable == "gust":
            st.caption(f"Rangos y valores expresados en {unidad}.")
            pintar_leyenda(rangos_viento_en_unidad(cargar_rangos("gust"), unidad), "Rachas de viento")
        elif tipo_variable == "tp":
            config = cargar_rangos("tp")
            st.caption("AYSEN_SCCZ y ANTARTICA se muestran en gris claro, sin paleta.")
            gris = config["color_sin_paleta"]
            st.markdown(_caja_color(gris["fondo"], gris["texto"], "AYSEN_SCCZ / ANTARTICA · sin paleta", 8),
                        unsafe_allow_html=True)
            pintar_leyenda(config, "Otras áreas")
            for area, nombre in (("INSULAR_NORTE", "INSULAR NORTE e INSULAR CENTRAL"),
                                 ("CORDILLERA_NORTE", "CORDILLERA NORTE")):
                config_area = {"rangos": config.get("rangos_por_area", {}).get(area, config["rangos"])}
                pintar_leyenda(config_area, nombre)
        else:
            config = cargar_rangos(tipo_variable)
            titulo = VARIABLES_METEO[tipo_variable].titulo_leyenda
            if tipo_variable == "gh_ceiling":
                config = rangos_base_nubes_en_unidad(config, unidad)
                titulo = f"Base de nubes · {unidad}"
            pintar_leyenda(config, titulo)
