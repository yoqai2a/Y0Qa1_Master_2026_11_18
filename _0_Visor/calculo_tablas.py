"""Cálculo de las tablas: períodos diarios, resúmenes por área y series temporales.

Hay una sola ruta de cálculo: los datos (de un NetCDF o del histórico) se normalizan a una
tabla de series (ver ``datos_ciclos``) y todo se calcula sobre esa tabla con ``groupby``.
Las funciones con caché de Streamlit están al final de cada bloque; las demás son puras.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd
import streamlit as st

import datos_ciclos as dc
from datos_ciclos import UTC, Punto
from variables_meteo import VARIABLES_METEO, a_unidad_visual

_POR_PUNTO = ["Área", "Punto"]


# --------------------------------------------------------------------------- tiempo
def fecha_hora(fecha: str, hora: str) -> datetime:
    """'20261119', '12' -> 2026-11-19 12:00 UTC (con zona)."""
    return datetime.strptime(fecha, "%Y%m%d").replace(tzinfo=UTC) + timedelta(hours=int(hora))


def periodo_diario(fecha: str, cierre: str) -> tuple[datetime, datetime]:
    """Período de 24 h que termina a la hora de cierre del día siguiente a ``fecha``."""
    hora_inicio = (int(cierre) + 1) % 24
    inicio = fecha_hora(fecha, f"{hora_inicio:02d}")
    fin = fecha_hora(fecha, cierre) + timedelta(days=1)
    return inicio, fin


def etiqueta_periodo(fecha: str, cierre: str, minimo: datetime, maximo: datetime) -> str:
    inicio, fin = periodo_diario(fecha, cierre)
    inicio_mostrado = max(inicio, minimo)
    incompleto = minimo > inicio or maximo < fin
    marca = "*" if incompleto else ""
    return f"{inicio_mostrado:%d_%m_%H}Z / {fin:%d_%m_%H}Z{marca}"


def formatea_isoterma(valor: float, centenas: bool) -> int:
    """Redondea la altura a metros enteros o a la centena más cercana."""
    if centenas:
        magnitud = int(np.floor(abs(float(valor)) / 100 + 0.5)) * 100
        return magnitud if valor >= 0 else -magnitud
    return int(round(float(valor)))


@st.cache_data(show_spinner=False)
def limites_temporales(ruta: str, mtime: float) -> tuple[datetime, datetime] | None:
    del mtime  # forma parte de la clave de caché: si el archivo cambia, se recalcula
    archivo = Path(ruta)
    if dc.es_historico(archivo):
        return dc.limites_historico(archivo)
    validas = dc.horas_validas_nc(archivo)
    return (min(validas), max(validas)) if validas else None


@st.cache_data(show_spinner=False)
def fechas_disponibles(ruta: str, mtime: float, cierre: str = "03") -> list[str]:
    limites = limites_temporales(ruta, mtime)
    if limites is None:
        return []
    minimo, maximo = limites
    dia, ultimo = minimo.date() - timedelta(days=1), maximo.date()
    fechas = []
    while dia <= ultimo:
        fecha = dia.strftime("%Y%m%d")
        comienzo, fin = periodo_diario(fecha, cierre)
        if comienzo <= maximo and fin >= minimo:
            fechas.append(fecha)
        dia += timedelta(days=1)
    return fechas


# --------------------------------------------------------------------------- datos
@st.cache_data(show_spinner=False, max_entries=24)
def series_variable(ruta: str, mtime: float, clave: str, puntos: tuple[Punto, ...]) -> pd.DataFrame:
    """Tabla de series de una variable (cacheada: NetCDF e histórico comparten la misma forma)."""
    del mtime
    return dc.cargar_series(Path(ruta), clave, puntos)


# --------------------------------------------------------------------------- máximos por período
def _a_visual(valor, clave: str, unidad: str):
    if valor is None:
        return None
    if isinstance(valor, tuple):
        return tuple(float(a_unidad_visual(v, clave, unidad)) for v in valor)
    return float(a_unidad_visual(float(valor), clave, unidad))


def _valores_por_punto(series: pd.DataFrame, horas: pd.Series, en_periodo: pd.Series, comienzo: datetime,
                       fecha: str, clave: str, formato_especial: bool) -> dict:
    """{(área, punto): valor} del período, en la unidad de almacenamiento."""
    periodo = series[en_periodo]
    definicion = VARIABLES_METEO[clave]
    if definicion.periodo == "acumulado":
        # Acumulada desde el inicio del ciclo: en períodos parciales la base es el primer valor
        # disponible; el valor final es el último disponible hasta el cierre.
        ultimo = periodo.groupby(_POR_PUNTO, sort=False)["Valor"].last()
        primero = periodo.groupby(_POR_PUNTO, sort=False)["Valor"].first()
        antes = series[horas <= comienzo].groupby(_POR_PUNTO, sort=False)["Valor"].last()
        base = antes.reindex(ultimo.index).fillna(primero)
        return (ultimo - base).clip(lower=0).to_dict()
    if definicion.periodo == "rango":
        if formato_especial:
            objetivos = (fecha_hora(fecha, "12"), fecha_hora(fecha, "00") + timedelta(days=1))
            pares = pd.concat(
                [series[horas == o].groupby(_POR_PUNTO, sort=False)["Valor"].first() for o in objetivos],
                axis=1, keys=[0, 1]).dropna()
            return {indice: (fila[0], fila[1]) for indice, fila in pares.iterrows()}
        resumen = periodo.groupby(_POR_PUNTO, sort=False)["Valor"].agg(["min", "max"])
        return {indice: (fila["min"], fila["max"]) for indice, fila in resumen.iterrows()}
    agrupado = periodo.groupby(_POR_PUNTO, sort=False)["Valor"]
    return (agrupado.min() if definicion.periodo == "min" else agrupado.max()).to_dict()


def calcular_maximos_series(series: pd.DataFrame, fechas: Sequence[str], cierre: str, clave: str,
                            unidad: str, formato_especial: bool, puntos: Sequence[Punto]) -> dict:
    """Valor por punto y por período diario.

    Devuelve ``{"valores": {fecha: {área: {punto: valor|None}}}, "errores": {fecha: texto},
    "variable": etiqueta}``. En la isoterma 0 el valor es un par (a, b).
    """
    definicion = VARIABLES_METEO[clave]
    if series.empty:
        raise ValueError(f"No hay datos para {definicion.etiqueta_historico}.")
    series = series.sort_values("FechaHoraUTC", kind="stable")
    horas = series["FechaHoraUTC"]
    especial = clave == "gh_iso0" and formato_especial
    resultados: dict[str, dict] = {fecha: {} for fecha in fechas}
    errores: dict[str, str] = {}

    for fecha in fechas:
        comienzo, fin = periodo_diario(fecha, cierre)
        en_periodo = (horas >= comienzo) & (horas <= fin)
        if especial:
            objetivos = (fecha_hora(fecha, "12"), fecha_hora(fecha, "00") + timedelta(days=1))
            if any(not (horas == objetivo).any() for objetivo in objetivos):
                errores[fecha] = "no están disponibles ambas horas del formato especial 12Z / 00Z"
                continue
        elif not en_periodo.any():
            errores[fecha] = ("no hay horas disponibles dentro del período" if clave == "tp"
                              else "no hay horas del pronóstico en el período")
            continue
        valores = _valores_por_punto(series, horas, en_periodo, comienzo, fecha, clave, formato_especial)
        for punto in puntos:
            valor = valores.get((punto.area, punto.punto))
            resultados[fecha].setdefault(punto.area, {})[punto.punto] = _a_visual(valor, clave, unidad)
    return {"valores": resultados, "errores": errores, "variable": definicion.etiqueta_historico}


@st.cache_data(show_spinner="Calculando máximos diarios por área…")
def calcular_maximos(ruta: str, mtime: float, fechas: tuple[str, ...], cierre: str,
                     tipo_variable: str, unidad: str, formato_especial: bool,
                     puntos: tuple[Punto, ...]) -> dict:
    series = series_variable(ruta, mtime, tipo_variable, puntos)
    return calcular_maximos_series(series, fechas, cierre, tipo_variable, unidad, formato_especial, puntos)


# --------------------------------------------------------------------------- resumen por área
def agregar_area(valores: Sequence, clave: str, formato_especial: bool):
    """Resume los puntos de un área: mínimo o máximo según la variable. None si no hay datos.

    Isoterma 0: par (a, b). Normal: (mínimo de mínimos, máximo de máximos); especial 12Z/00Z:
    (máximo de las 12Z, máximo de las 00Z).
    """
    validos = [v for v in valores if v is not None]
    if not validos:
        return None
    if clave == "gh_iso0":
        if formato_especial:
            return max(v[0] for v in validos), max(v[1] for v in validos)
        return min(v[0] for v in validos), max(v[1] for v in validos)
    return min(validos) if VARIABLES_METEO[clave].agrega_minimo_por_area else max(validos)


def resumen_area(datos: dict, fecha: str, area: str, clave: str, formato_especial: bool):
    """Valor resumen de un área en un período (None si el período tuvo error o no hay datos)."""
    if fecha in datos["errores"]:
        return None
    por_punto = datos["valores"].get(fecha, {}).get(area, {})
    return agregar_area(list(por_punto.values()), clave, formato_especial)


def filas_resumen_y_detalle(datos: dict, puntos: Sequence[Punto], fechas: Sequence[str],
                            etiquetas: dict[str, str], clave: str, formato_especial: bool,
                            aproximar_centenas: bool) -> tuple[list[dict], dict[str, list[dict]]]:
    """Filas listas para mostrar: resumen por área y detalle por punto de cada área."""
    def texto_par(par):
        return (f"{formatea_isoterma(par[0], aproximar_centenas)} / "
                f"{formatea_isoterma(par[1], aproximar_centenas)}")

    areas = list(dict.fromkeys(p.area for p in puntos))
    resumen: list[dict] = []
    detalle_por_area: dict[str, list[dict]] = {}
    for area in areas:
        detalle = []
        for p in (p for p in puntos if p.area == area):
            fila_punto = {"Punto": p.punto}
            for fecha in fechas:
                valor = datos["valores"].get(fecha, {}).get(area, {}).get(p.punto)
                if fecha in datos["errores"]:
                    valor = None
                if clave == "gh_iso0" and valor is not None:
                    valor = texto_par(valor)
                fila_punto[etiquetas[fecha]] = valor
            detalle.append(fila_punto)
        fila_area = {"Área": area}
        for fecha in fechas:
            valor = resumen_area(datos, fecha, area, clave, formato_especial)
            if clave == "gh_iso0" and valor is not None:
                valor = texto_par(valor)
            fila_area[etiquetas[fecha]] = valor
        resumen.append(fila_area)
        detalle_por_area[area] = detalle
    return resumen, detalle_por_area


# --------------------------------------------------------------------------- serie temporal
@st.cache_data(show_spinner="Leyendo la serie del punto…")
def calcular_serie_temporal(ruta: str, mtime: float, tipo_variable: str, unidad: str,
                            area: str, punto: str, aproximar_centenas: bool,
                            puntos: tuple[Punto, ...]) -> list[dict]:
    """Serie completa de un punto: [{"Fecha": datetime UTC, "Valor": int}, ...]."""
    series = series_variable(ruta, mtime, tipo_variable, puntos)
    serie = series[(series["Área"] == area) & (series["Punto"] == punto)].sort_values("FechaHoraUTC")
    valores = a_unidad_visual(serie["Valor"].to_numpy(dtype=float), tipo_variable, unidad)
    salida = []
    for fecha, valor in zip(serie["FechaHoraUTC"], valores):
        if tipo_variable == "gh_iso0":
            entero = formatea_isoterma(float(valor), aproximar_centenas)
        else:
            entero = int(round(float(valor)))
        salida.append({"Fecha": fecha.to_pydatetime(), "Valor": entero})
    return salida
