"""Pantalla de la pestaña Corte temporal (tiempo x presión para cada punto)."""
from __future__ import annotations

import streamlit as st

import datos_ciclos as dc
from errores import mostrar_error

from . import calculo, grafico
from . import datos as dt
from .config import ARCHIVO_PUNTOS, ESCALAS_VERTICALES, ConfigCorte, ErrorConfigCorte, cargar_config

_ETIQUETA_ESCALA = {"lineal": "Presión lineal", "logaritmica": "Presión logarítmica"}


@st.cache_data(show_spinner="Leyendo el perfil del punto…", max_entries=48)
def _perfil(clave: str, firma: float, area: str, nombre: str, lat: float, lon: float,
            capas: tuple, _cfg: ConfigCorte):
    """Perfil de un punto (cacheado). ``capas`` y ``firma`` invalidan la caché al cambiar la configuración o los archivos."""
    del firma, capas
    perfil = dt.cargar_perfil_punto(clave, _cfg, dc.Punto(area, nombre, lat, lon))
    return perfil.tabla, perfil.fuente, perfil.capas_faltantes


@st.cache_data(show_spinner="Dibujando el corte…", max_entries=48)
def _imagen(clave: str, firma: float, area: str, nombre: str, lat: float, lon: float, capas: tuple,
            variable: str, vista: str, unidad: str, presion_superior: float, presion_inferior: float,
            escala: str, barbas: bool, _cfg: ConfigCorte) -> tuple[bytes, bytes]:
    """(PNG, CSV) del corte pedido."""
    tabla, _, _ = _perfil(clave, firma, area, nombre, lat, lon, capas, _cfg)
    definicion = _cfg.variables[variable].vistas[vista]
    seccion = calculo.construir_seccion(tabla, definicion, unidad, _cfg).recortar(presion_superior, presion_inferior)
    titulo = f"{vista} ({unidad}) · {area} / {nombre}"
    subtitulo = f"Ciclo {clave[:8]} {clave[9:]}Z · lat {lat:.2f}° lon {lon:.2f}°"
    figura = grafico.figura_corte(seccion, definicion, titulo, subtitulo, escala, barbas)
    return grafico.a_png(figura), seccion.a_tabla().to_csv().encode("utf-8-sig")


def _controles_punto(puntos: tuple[dc.Punto, ...], ciclos: list[str]) -> tuple[str, dc.Punto]:
    areas = list(dict.fromkeys(p.area for p in puntos))
    col_ciclo, col_area, col_punto = st.columns([1.6, 2, 2])
    with col_ciclo:
        clave = st.selectbox("Ciclo", ciclos, format_func=lambda v: f"{v[:8]} · {v[9:]}Z", key="corte_ciclo")
    with col_area:
        area = st.selectbox("Área", areas, key="corte_area")
    with col_punto:
        nombres = [p.punto for p in puntos if p.area == area]
        nombre = st.selectbox("Punto", nombres, key=f"corte_punto_{area}")
    return clave, next(p for p in puntos if p.area == area and p.punto == nombre)


def mostrar_corte_temporal() -> None:
    st.subheader("Corte temporal · tiempo x presión")
    try:
        cfg = cargar_config()
        puntos = dc.cargar_puntos(ARCHIVO_PUNTOS)
    except (ErrorConfigCorte, OSError, ValueError, KeyError) as exc:
        mostrar_error("La configuración de Corte temporal no es válida. Revisa la carpeta "
                      "_0_Visor/corte_temporal/configuracion.", exc)
        return
    if not puntos:
        st.warning("No hay puntos en corte_temporal/configuracion/puntos.json.")
        return
    ciclos = dt.listar_ciclos_corte(cfg)
    if not ciclos:
        st.warning("No se encontraron capas NetCDF (t, r, u, v por nivel) ni respaldo de perfiles. "
                   "Se generan al ejecutar la descarga con _2_CreaNC (capas_nc.json).")
        return

    clave, punto = _controles_punto(puntos, ciclos)

    col_var, col_vista, col_unidad = st.columns([2, 3, 1.2])
    with col_var:
        variable = st.selectbox("Variable", list(cfg.variables), key="corte_variable")
    vistas = cfg.variables[variable].vistas
    with col_vista:
        vista = st.selectbox("Vista", list(vistas), key=f"corte_vista_{variable}", disabled=len(vistas) == 1)
    definicion = vistas[vista]
    with col_unidad:
        unidad = st.selectbox("Unidad", list(definicion.unidades), key=f"corte_unidad_{variable}_{vista}",
                              disabled=len(definicion.unidades) == 1)

    niveles = sorted(set.intersection(*(set(cfg.niveles_por_capa.get(c, ())) for c in definicion.capas_necesarias)))
    col_rango, col_escala, col_barbas = st.columns([3, 2, 1.5])
    with col_rango:
        presion_superior, presion_inferior = st.select_slider(
            "Rango de presión (hPa)", options=niveles, value=(niveles[0], niveles[-1]),
            key=f"corte_rango_{variable}_{vista}", help="Arriba: menor presión. Abajo: mayor presión.")
    with col_escala:
        escala = st.radio("Eje vertical", ESCALAS_VERTICALES, format_func=_ETIQUETA_ESCALA.get, horizontal=True,
                          index=ESCALAS_VERTICALES.index(cfg.escala_vertical_defecto), key="corte_escala")
    with col_barbas:
        barbas = st.toggle("Barbas de viento", value=True, key="corte_barbas", disabled=not definicion.barbas)

    firma = dt.firma_fuente(clave)
    capas = tuple(cfg.todas_las_capas)
    tabla, fuente, faltantes = _perfil(clave, firma, punto.area, punto.punto, punto.lat, punto.lon, capas, cfg)
    if tabla.empty:
        st.warning(
            f"El punto {punto.area} / {punto.punto} no tiene datos en el ciclo {clave}. Lo más probable es que "
            "quede fuera del área descargada (norte, sur, oeste y este en __Configuracion_Fnnn.toml). "
            "Si acabas de agregarlo y tienes los NetCDF, regenera el respaldo con: "
            "python _0_Visor/archivar_corte.py --todos")
        return
    if faltantes:
        st.warning(f"Faltan {len(faltantes)} capas NetCDF de este ciclo ({', '.join(faltantes[:4])}"
                   f"{'…' if len(faltantes) > 4 else ''}); el corte puede estar incompleto.")
    try:
        png, csv = _imagen(clave, firma, punto.area, punto.punto, punto.lat, punto.lon, capas, variable, vista,
                           unidad, presion_superior, presion_inferior, escala, barbas, cfg)
    except ValueError as exc:
        st.info(f"No se puede dibujar este corte: {exc}")
        return

    st.image(png, use_container_width=True)
    horas = tabla["FechaHoraUTC"]
    origen = ("capas NetCDF (con los puntos actuales)" if fuente == "NetCDF"
              else "respaldo de perfiles (___Historico_Corte)")
    st.caption(f"Ciclo {clave[:8]} {clave[9:]}Z · pronóstico del {horas.min():%d-%m %H}Z al {horas.max():%d-%m %H}Z · "
               f"fuente: {origen} · hora UTC")
    nombre_base = f"Y0Qa1_corte_{punto.punto}_{variable}_{unidad}_{clave}Z".replace(" ", "_").replace("/", "-")
    col_png, col_csv, _ = st.columns([1, 1, 4])
    with col_png:
        st.download_button("Descargar imagen", png, file_name=nombre_base + ".png", mime="image/png",
                           use_container_width=True, key="corte_descargar_png")
    with col_csv:
        st.download_button("Descargar datos", csv, file_name=nombre_base + ".csv", mime="text/csv",
                           use_container_width=True, key="corte_descargar_csv")
