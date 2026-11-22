"""Pestaña Tablas: resúmenes diarios por área, detalle por punto, serie temporal y exportación.

Aquí solo vive la interfaz. Los datos están en ``datos.py``, el cálculo en ``calculo.py``,
los colores en ``estilos.py``, las definiciones de variables en ``variables.py`` y el PDF en ``pdf.py``
(todos en esta misma carpeta).
"""
from __future__ import annotations

import io
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

from errores import mostrar_error

from . import calculo as ct
from . import datos as dc
from . import estilos as et
from .variables import HORAS_CIERRE, VARIABLES, VARIABLES_METEO


# --------------------------------------------------------------------------- controles
def _controles_tablas(ciclos: list[tuple[str, Path]]) -> tuple[str, str, str, str, bool, bool]:
    ciclo_labels = {clave: f"{clave[:8]} · {clave[9:]}Z" for clave, _ in ciclos}
    opciones_ciclo = [clave for clave, _ in ciclos]
    if st.session_state.get("tablas_ciclo") not in opciones_ciclo:
        st.session_state["tablas_ciclo"] = opciones_ciclo[0]
    st.session_state.setdefault("tablas_variable", "Racha de viento")
    if "tablas_cierre" not in st.session_state:
        st.session_state["tablas_cierre"] = dc.cargar_cierre_global()

    col_ciclo, col_cierre, col_variable, col_unidad, col_leyenda = st.columns([2, 1, 2.6, 1, 1])
    with col_ciclo:
        ciclo = st.selectbox("Ciclo", opciones_ciclo, format_func=lambda v: ciclo_labels[v],
                             key="tablas_ciclo", label_visibility="collapsed")
    with col_cierre:
        cierre = st.selectbox("Cierre UTC", HORAS_CIERRE, format_func=lambda v: f"{v}Z",
                              key="tablas_cierre", label_visibility="collapsed")
    with col_variable:
        variable = st.selectbox("Variable", tuple(VARIABLES), key="tablas_variable",
                                label_visibility="collapsed")
    tipo_variable = VARIABLES[variable]
    definicion = VARIABLES_METEO[tipo_variable]
    key_unidad = f"tablas_unidad_{tipo_variable}"
    st.session_state.setdefault(key_unidad, definicion.unidad_defecto)
    with col_unidad:
        unidad = st.selectbox("Unidad", definicion.unidades, key=key_unidad, label_visibility="collapsed")
    with col_leyenda:
        et.mostrar_leyenda(tipo_variable, unidad)

    formato_especial = aproximar_centenas = False
    if tipo_variable == "gh_iso0":
        col_a, col_b, _ = st.columns([1.4, 1.4, 4])
        with col_a:
            formato_especial = st.toggle(
                "Formato especial 12Z / 00Z", key="tablas_formato_especial",
                help="Muestra las alturas de isoterma 0 a las 12Z del día y 00Z del día siguiente.")
        with col_b:
            aproximar_centenas = st.toggle(
                "Aproximar a centenas", value=True, key="tablas_aproximar_centenas",
                help="Redondea los valores de isoterma 0 a la centena de metros más cercana.")
    return ciclo, cierre, variable, unidad, formato_especial, aproximar_centenas


def _acciones(ciclo: str, cierre: str, formato_especial: bool, aproximar_centenas: bool,
              resumen: list[dict], detalle_por_area: dict[str, list[dict]], tipo_variable: str,
              unidad: str) -> None:
    """Acciones secundarias (guardar cierre, PDF y exportar) agrupadas en un panel plegable."""
    with st.expander("Acciones y exportación"):
        col_cierre, col_pdf, col_csv, col_excel = st.columns(4)
        with col_cierre:
            if st.button("Guardar cierre", use_container_width=True,
                         help="Recuerda la hora de cierre elegida como valor inicial."):
                try:
                    dc.guardar_cierre_global(cierre)
                    st.success(f"Cierre {cierre}Z guardado.")
                except OSError as exc:
                    mostrar_error("No se pudo guardar el cierre.", exc)
        clave_pdf = (ciclo, cierre, formato_especial, aproximar_centenas)
        with col_pdf:
            if st.button("Crear PDF", use_container_width=True, key="crear_pdf_tablas"):
                try:
                    from .pdf import generar_pdf_tablas
                    with st.spinner("Preparando las cuatro tablas para imprimir…"):
                        contenido = generar_pdf_tablas(ciclo, cierre, formato_especial, aproximar_centenas)
                    st.session_state["pdf_tablas_generado"] = {"clave": clave_pdf, "contenido": contenido}
                except Exception as exc:
                    st.session_state.pop("pdf_tablas_generado", None)
                    mostrar_error("No se pudo crear el PDF.", exc)
            generado = st.session_state.get("pdf_tablas_generado", {})
            if generado.get("clave") == clave_pdf:
                st.download_button("Descargar PDF", data=generado["contenido"],
                                   file_name=f"Y0Qa1_Tablas_{ciclo}_{cierre}Z.pdf", mime="application/pdf",
                                   use_container_width=True, key="descargar_pdf_tablas")
        resumen_df = _tabla_exportable(resumen)
        nombre = f"Y0Qa1_{tipo_variable}_{unidad.replace('/', '-')}_{ciclo}_{cierre}Z"
        with col_csv:
            st.download_button("Exportar CSV", data=resumen_df.to_csv(index=False).encode("utf-8-sig"),
                               file_name=nombre + ".csv", mime="text/csv", use_container_width=True,
                               key="exportar_csv_tablas", help="Resumen por área de la tabla en pantalla.")
        with col_excel:
            st.download_button("Exportar Excel", data=_excel(resumen_df, detalle_por_area),
                               file_name=nombre + ".xlsx", use_container_width=True,
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               key="exportar_excel_tablas",
                               help="Hojas: resumen por área y detalle de todos los puntos.")


def _tabla_exportable(filas: list[dict]) -> pd.DataFrame:
    tabla = pd.DataFrame(filas)
    for columna in tabla.columns[1:]:
        if pd.api.types.is_numeric_dtype(tabla[columna]):
            tabla[columna] = tabla[columna].round(0)
    return tabla


def _excel(resumen: pd.DataFrame, detalle_por_area: dict[str, list[dict]]) -> bytes:
    detalle = pd.concat(
        [_tabla_exportable(filas).assign(**{"Área": area}) for area, filas in detalle_por_area.items()],
        ignore_index=True)
    detalle = detalle[["Área", *[c for c in detalle.columns if c != "Área"]]]
    memoria = io.BytesIO()
    with pd.ExcelWriter(memoria, engine="openpyxl") as escritor:
        resumen.to_excel(escritor, sheet_name="Resumen por área", index=False)
        detalle.to_excel(escritor, sheet_name="Detalle por punto", index=False)
    return memoria.getvalue()


def _caption_datos(ruta: Path, ciclo: str, limites: tuple[datetime, datetime]) -> None:
    """Cuándo son y de dónde vienen los datos que se están viendo."""
    minimo, maximo = limites
    modificado = datetime.fromtimestamp(ruta.stat().st_mtime, tz=timezone.utc)
    st.caption(
        f"Ciclo {ciclo[:8]} {ciclo[9:]}Z · pronóstico disponible del {minimo:%d-%m %H}Z al {maximo:%d-%m %H}Z · "
        f"archivo modificado el {modificado:%d-%m-%Y %H:%M} UTC")


# --------------------------------------------------------------------------- pantalla
def mostrar_tablas() -> None:
    ciclos = dc.listar_ciclos()
    if not ciclos:
        st.warning("No se encontraron NetCDF locales ni históricos de ciclos.")
        return

    ciclo, cierre, variable, unidad, formato_especial, aproximar_centenas = _controles_tablas(ciclos)
    tipo_variable = VARIABLES[variable]
    ruta = dc.ruta_variable(ciclo, tipo_variable)
    if ruta is None:
        if tipo_variable == "tp":
            st.warning(f"No se encontró precipitación total (*tp_sfc*, incluido msg597) para el ciclo {ciclo}.")
        else:
            st.warning(f"No se encontró el archivo {variable} para el ciclo {ciclo}.")
        return

    mtime = ruta.stat().st_mtime
    try:
        limites = ct.limites_temporales(str(ruta), mtime)
        fechas = tuple(ct.fechas_disponibles(str(ruta), mtime, cierre=cierre))
        if not fechas:
            inicio_periodo, fin_periodo = ct.periodo_diario("20000101", cierre)
            st.info(f"Este ciclo no contiene horas entre {inicio_periodo:%HZ} y {fin_periodo:%HZ} del día siguiente.")
            return
        if limites is None:
            st.info("El archivo no contiene horas válidas.")
            return
        puntos = dc.cargar_puntos()
        datos = ct.calcular_maximos(str(ruta), mtime, fechas, cierre, tipo_variable, unidad,
                                    formato_especial, puntos)
        config_colores = et.config_colores(tipo_variable, unidad)
    except Exception as exc:
        mostrar_error("No se pudieron leer los datos de este ciclo.", exc)
        return

    _caption_datos(ruta, ciclo, limites)
    etiquetas = {fecha: ct.etiqueta_periodo(fecha, cierre, *limites) for fecha in fechas}
    resumen, detalle_por_area = ct.filas_resumen_y_detalle(
        datos, puntos, fechas, etiquetas, tipo_variable, formato_especial, aproximar_centenas)
    escala = et.escala_de_color(tipo_variable, unidad)

    _acciones(ciclo, cierre, formato_especial, aproximar_centenas, resumen, detalle_por_area,
              tipo_variable, unidad)

    evento_area = st.dataframe(
        et.tabla_con_colores(resumen, tipo_variable, config_colores, escala=escala),
        use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row",
        key=f"tabla_areas_{ciclo}_{tipo_variable}",
    )
    definicion = VARIABLES_METEO[tipo_variable]
    if tipo_variable == "gh_iso0":
        resumen_agregacion = (
            "Modo especial: máximos a las 12Z del día / 00Z del día siguiente."
            if formato_especial else "Mínimo / máximo del período diario, usando las horas disponibles.")
    elif definicion.agrega_minimo_por_area:
        resumen_agregacion = "La tabla muestra los valores mínimos por área."
    else:
        resumen_agregacion = "La tabla muestra los valores máximos por área."
    st.caption(f"{resumen_agregacion} · Variable: {variable} · unidades {unidad} · archivo {ruta.name}")

    filas_area = list(evento_area.selection.rows)
    if filas_area:
        area = resumen[filas_area[0]]["Área"]
        st.markdown(f"#### {area} · detalle de puntos")
        evento_punto = st.dataframe(
            et.tabla_con_colores(detalle_por_area[area], tipo_variable, config_colores,
                                 escala=escala, area_detalle=area),
            use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row",
            key=f"tabla_puntos_{ciclo}_{tipo_variable}_{area}",
        )
        filas_punto = list(evento_punto.selection.rows)
        if filas_punto:
            punto = detalle_por_area[area][filas_punto[0]]["Punto"]
            try:
                serie = ct.calcular_serie_temporal(str(ruta), mtime, tipo_variable, unidad, area, punto,
                                                   aproximar_centenas, puntos)
                st.markdown(f"#### Serie temporal completa · {punto}")
                if serie:
                    grafico = pd.DataFrame(serie)
                    grafico["Fecha"] = pd.to_datetime(grafico["Fecha"]).dt.tz_localize(None)  # hora UTC
                    st.line_chart(grafico.set_index("Fecha"), y="Valor", y_label=unidad, width="stretch")
                    st.caption(definicion.descripcion_serie)
                else:
                    st.info("No hay valores disponibles para graficar en este punto.")
            except Exception as exc:
                mostrar_error("No se pudo calcular la serie temporal.", exc)

    if datos["errores"]:
        avisos = [f"{etiquetas[fecha]}: {error}" for fecha, error in datos["errores"].items()]
        st.warning("No se pudo calcular el período completo para: " + "; ".join(avisos))
