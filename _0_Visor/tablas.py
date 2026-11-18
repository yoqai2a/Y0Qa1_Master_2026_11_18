"""Resúmenes diarios de viento, precipitación e isoterma 0 por áreas."""
from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
from netCDF4 import Dataset


RAIZ_PROYECTO = Path(__file__).resolve().parent.parent
DIR_NC = RAIZ_PROYECTO / "___Data" / "___NC"
DIR_HISTORICO = RAIZ_PROYECTO / "___Data" / "___Historico"
ARCHIVO_PUNTOS = Path(__file__).with_name("Puntos.json")
ARCHIVO_CIERRES = Path(__file__).with_name("cierres_tablas.json")
ARCHIVOS_COLORES = {
    "gust": Path(__file__).with_name("rangos_viento.json"),
    "tp": Path(__file__).with_name("rangos_precipitacion.json"),
}
HORAS_CIERRE = tuple(f"{hora:02d}" for hora in range(0, 24, 3))
VARIABLES = {
    "Racha de viento": "gust",
    "Precipitación total (msg597 / tp)": "tp",
    "Isoterma 0 (gh_iso0)": "gh_iso0",
}
UNIDADES_VIENTO = ("km/h", "kt", "m/s")
FACTORES_VIENTO = {"km/h": 3.6, "kt": 1.94384449244, "m/s": 1.0}


def _formatea_isoterma(valor: float, centenas: bool) -> int:
    """Redondea la altura a metros enteros o a la centena más cercana."""
    if centenas:
        magnitud = int(np.floor(abs(float(valor)) / 100 + 0.5)) * 100
        return magnitud if valor >= 0 else -magnitud
    return int(round(float(valor)))


def listar_ciclos() -> list[tuple[str, Path]]:
    """Encuentra ciclos locales que incluyen el NetCDF de rachas."""
    ciclos: dict[str, Path] = {}
    if DIR_NC.is_dir():
        for archivo in DIR_NC.glob("*/*/*gust*.nc"):
            fecha, ciclo = archivo.parent.parent.name, archivo.parent.name
            try:
                datetime.strptime(fecha, "%Y%m%d")
            except ValueError:
                continue
            if ciclo in {"00", "06", "12", "18"}:
                ciclos[f"{fecha}_{ciclo}"] = archivo
    return sorted(ciclos.items(), reverse=True)


def ruta_variable(clave_ciclo: str, variable: str) -> Path | None:
    fecha, ciclo = clave_ciclo.split("_")
    carpeta = DIR_NC / fecha / ciclo
    if variable == "gust":
        coincidencias = sorted(carpeta.glob("*gust*.nc"))
    elif variable == "tp":
        coincidencias = sorted(carpeta.glob("*tp_sfc*msg597*.nc"))
        if not coincidencias:
            # El número de mensaje GRIB puede cambiar según la edición del ciclo;
            # tp_sfc es el nombre NetCDF estable de precipitación total.
            coincidencias = sorted(carpeta.glob("*tp_sfc*.nc"))
    else:
        coincidencias = sorted(carpeta.glob("*gh_iso0*msg416*.nc"))
        if not coincidencias:
            coincidencias = sorted(carpeta.glob("*gh_iso0*.nc"))
    return coincidencias[0] if coincidencias else None


def guardar_historico_ciclo(clave_ciclo: str, puntos: list[dict]) -> tuple[Path, int, list[str]]:
    """Guarda en un CSV todas las series disponibles de puntos y variables del ciclo."""
    variables = (
        ("gust", "Racha de viento", "km/h", 3.6),
        ("tp", "Precipitación total", "mm", 1.0),
        ("gh_iso0", "Isoterma 0", "m", 1.0),
    )
    filas: list[dict] = []
    faltantes: list[str] = []
    for tipo, etiqueta, unidad, factor in variables:
        ruta = ruta_variable(clave_ciclo, tipo)
        if ruta is None:
            faltantes.append(etiqueta)
            continue
        with Dataset(ruta, "r") as ds:
            inicio = _inicio_ciclo(ds)
            horas = np.asarray(ds.variables["forecast_hour"][:], dtype=float)
            fechas_horas = [inicio + timedelta(hours=float(hora)) for hora in horas]
            nombres_coordenadas = ("latitude", "longitude")
            if any(nombre not in ds.variables for nombre in nombres_coordenadas):
                raise ValueError(f"{ruta.name} no contiene latitude/longitude.")
            latitudes = np.asarray(ds.variables["latitude"][:], dtype=float)
            longitudes = ((np.asarray(ds.variables["longitude"][:], dtype=float) + 180) % 360) - 180
            objetivo = tipo
            coincidencias = [
                variable for nombre, variable in ds.variables.items()
                if str(getattr(variable, "GRIB_shortName", "")).casefold() == objetivo
                or nombre.casefold().startswith(
                    ("gust",) if tipo == "gust" else ("tp_", "tp") if tipo == "tp" else ("gh_iso0",)
                )
            ]
            if not coincidencias:
                raise ValueError(f"No se encontró la variable {tipo} dentro de {ruta.name}.")
            variable = coincidencias[0]
            for punto in puntos:
                iy = int(np.nanargmin(np.abs(latitudes - punto["lat"])))
                lon_objetivo = ((punto["lon"] + 180) % 360) - 180
                ix = int(np.nanargmin(np.abs(((longitudes - lon_objetivo + 180) % 360) - 180)))
                serie = np.ma.asarray(variable[:, iy, ix], dtype=float).filled(np.nan)
                for fecha_hora, valor in zip(fechas_horas, serie):
                    if not np.isfinite(valor):
                        continue
                    filas.append({
                        "Ciclo": clave_ciclo + "Z",
                        "FechaHoraUTC": fecha_hora.strftime("%Y-%m-%d %H:%M"),
                        "Área": punto["area"],
                        "Punto": punto["punto"],
                        "Latitud": punto["lat"],
                        "Longitud": punto["lon"],
                        "Variable": etiqueta,
                        "Valor": float(valor) * factor,
                        "Unidad": unidad,
                        "ArchivoNetCDF": ruta.name,
                    })

    DIR_HISTORICO.mkdir(parents=True, exist_ok=True)
    destino = DIR_HISTORICO / f"{clave_ciclo}Z.csv"
    temporal = destino.with_name(destino.name + ".part")
    columnas = ("Ciclo", "FechaHoraUTC", "Área", "Punto", "Latitud", "Longitud",
                "Variable", "Valor", "Unidad", "ArchivoNetCDF")
    try:
        with temporal.open("w", encoding="utf-8-sig", newline="") as archivo:
            escritor = csv.DictWriter(archivo, fieldnames=columnas)
            escritor.writeheader()
            escritor.writerows(filas)
        os.replace(temporal, destino)
    finally:
        if temporal.exists():
            temporal.unlink()
    return destino, len(filas), faltantes


def cargar_puntos() -> list[dict]:
    datos = json.loads(ARCHIVO_PUNTOS.read_text(encoding="utf-8"))
    return [
        {"area": area, "punto": nombre, "lat": float(coord["lat"]), "lon": float(coord["lon"])}
        for area, puntos in datos.items()
        for nombre, coord in puntos.items()
    ]


def cargar_cierres() -> dict[str, str]:
    try:
        datos = json.loads(ARCHIVO_CIERRES.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}
    if not isinstance(datos, dict):
        return {}
    return {str(fecha): str(hora) for fecha, hora in datos.items() if str(hora) in HORAS_CIERRE}


def cargar_cierre_global() -> str:
    return cargar_cierres().get("_global", "03")


def guardar_cierre_global(hora: str) -> None:
    cierres = cargar_cierres()
    cierres["_global"] = hora
    temporal = ARCHIVO_CIERRES.with_name(ARCHIVO_CIERRES.name + ".part")
    temporal.write_text(json.dumps(cierres, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporal, ARCHIVO_CIERRES)


def cargar_rangos(tipo_variable: str) -> dict:
    ruta = ARCHIVOS_COLORES[tipo_variable]
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    if not isinstance(datos.get("rangos"), list) or not datos["rangos"]:
        raise ValueError(f"El archivo {ruta.name} no contiene rangos válidos.")
    return datos


def _color_de(valor, rangos: list[dict]) -> tuple[str, str]:
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


def _tabla_con_colores(filas: list[dict], tipo_variable: str, config: dict | None = None,
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
                    resultado[indice] = (
                        f"background-color: {gris['fondo']}; color: {gris['texto']}; font-weight: 600"
                    )
            return resultado
        rangos = config.get("rangos_por_area", {}).get(area, config["rangos"])
        for indice, columna in enumerate(fila.index):
            if columna not in columnas_valores or pd.isna(fila[columna]):
                continue
            fondo, texto = _color_de(float(fila[columna]) * escala, rangos)
            if fondo:
                resultado[indice] = f"background-color: {fondo}; color: {texto}; font-weight: 600"
        return resultado

    return tabla.style.apply(estilos, axis=1).format(precision=0, na_rep="—")


def _pintar_leyenda(config: dict, titulo: str) -> None:
    st.markdown(f"**{titulo}**")
    rangos = config["rangos"]
    columnas = st.columns(len(rangos))
    for columna, rango in zip(columnas, rangos):
        with columna:
            st.markdown(
                f"<div style='padding:5px 6px;margin-bottom:5px;background:{rango['fondo']};"
                f"color:{rango['texto']};border:1px solid #cbd5e1;border-radius:4px;text-align:center'>"
                f"{rango['etiqueta']}</div>", unsafe_allow_html=True,
            )


def rangos_viento_en_unidad(config: dict, unidad: str) -> dict:
    """Convierte los límites almacenados en km/h a la unidad que muestra la tabla."""
    factor = FACTORES_VIENTO[unidad] / FACTORES_VIENTO["km/h"]
    convertidos = []
    for rango in config["rangos"]:
        minimo = None if rango["minimo"] is None else rango["minimo"] * factor
        maximo = None if rango["maximo"] is None else rango["maximo"] * factor

        def formato(valor):
            if valor is None:
                return ""
            return str(int(round(valor))) if abs(valor - round(valor)) < 1e-9 else f"{valor:.1f}"

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


def _mostrar_leyenda(tipo_variable: str, unidad: str) -> None:
    with st.popover("Leyendas", use_container_width=True):
        if tipo_variable == "gh_iso0":
            st.caption("La isoterma 0 no utiliza paleta de colores.")
        elif tipo_variable == "gust":
            config = rangos_viento_en_unidad(cargar_rangos("gust"), unidad)
            st.caption(f"Rangos y valores expresados en {unidad}.")
            _pintar_leyenda(config, "Rachas de viento")
        else:
            config = cargar_rangos("tp")
            st.caption("AYSEN_SCCZ y ANTARTICA se muestran en gris claro, sin paleta.")
            gris = config["color_sin_paleta"]
            st.markdown(
                f"<div style='padding:5px 6px;margin-bottom:8px;background:{gris['fondo']};"
                f"color:{gris['texto']};border:1px solid #cbd5e1;border-radius:4px;text-align:center'>"
                "AYSEN_SCCZ / ANTARTICA · sin paleta</div>", unsafe_allow_html=True,
            )
            _pintar_leyenda(config, "Otras áreas")
            for area, nombre in (("INSULAR_NORTE", "INSULAR NORTE e INSULAR CENTRAL"),
                                 ("CORDILLERA_NORTE", "CORDILLERA NORTE")):
                config_area = {"rangos": config.get("rangos_por_area", {}).get(area, config["rangos"])}
                _pintar_leyenda(config_area, nombre)


def _inicio_ciclo(ds) -> datetime:
    fecha = str(ds.getncattr("initialization_date"))
    ciclo = str(ds.getncattr("initialization_cycle_utc")).replace("Z", "")
    return datetime.strptime(fecha + ciclo.zfill(2), "%Y%m%d%H")


def _fecha_hora(fecha: str, hora: str) -> datetime:
    return datetime.strptime(fecha, "%Y%m%d") + timedelta(hours=int(hora))


@st.cache_data(show_spinner=False)
def fechas_disponibles(ruta: str, mtime: float) -> list[str]:
    del mtime  # el valor también forma parte de la clave de caché
    with Dataset(ruta, "r") as ds:
        base = _inicio_ciclo(ds)
        leads = np.asarray(ds.variables["forecast_hour"][:], dtype=float)
        validas = [base + timedelta(hours=float(lead)) for lead in leads]
    if not validas:
        return []
    minimo, maximo = min(validas), max(validas)
    dia, ultimo = minimo.date(), maximo.date()
    fechas = []
    while dia <= ultimo:
        fecha = dia.strftime("%Y%m%d")
        comienzo = _fecha_hora(fecha, "04")
        cierre_default = _fecha_hora(fecha, "03") + timedelta(days=1)
        if minimo <= comienzo and cierre_default <= maximo:
            fechas.append(fecha)
        dia += timedelta(days=1)
    return fechas


@st.cache_data(show_spinner="Calculando máximos diarios por área…")
def calcular_maximos(ruta: str, mtime: float, fechas: tuple[str, ...], cierre: str,
                     tipo_variable: str, unidad: str, formato_especial: bool,
                     puntos: tuple[tuple[str, str, float, float], ...]) -> dict:
    del mtime  # el valor también forma parte de la clave de caché
    resultados = {fecha: {} for fecha in fechas}
    errores = {}

    with Dataset(ruta, "r") as ds:
        inicio_ciclo = _inicio_ciclo(ds)
        leads = np.asarray(ds.variables["forecast_hour"][:], dtype=float)
        validas = [inicio_ciclo + timedelta(hours=float(lead)) for lead in leads]
        if not validas:
            raise ValueError("El archivo no contiene horas de pronóstico.")

        nombres = ("latitude", "longitude", "forecast_hour")
        if any(nombre not in ds.variables for nombre in nombres):
            raise ValueError("Al NetCDF le faltan las coordenadas o forecast_hour.")
        latitudes = np.asarray(ds.variables["latitude"][:], dtype=float)
        longitudes = np.asarray(ds.variables["longitude"][:], dtype=float)
        lon_normalizadas = ((longitudes + 180) % 360) - 180
        objetivo = tipo_variable
        coincidencias = [
            (nombre, variable) for nombre, variable in ds.variables.items()
            if str(getattr(variable, "GRIB_shortName", "")).casefold() == objetivo
            or nombre.casefold().startswith(
                ("gust",) if objetivo == "gust" else ("tp_", "tp") if objetivo == "tp" else ("gh_iso0",)
            )
        ]
        if not coincidencias:
            raise ValueError(f"No se encontró la variable NetCDF {objetivo}.")
        nombre_variable, variable = coincidencias[0]

        puntos_indices = []
        for area, punto, lat, lon in puntos:
            iy = int(np.nanargmin(np.abs(latitudes - lat)))
            lon_objetivo = ((lon + 180) % 360) - 180
            ix = int(np.nanargmin(np.abs(((lon_normalizadas - lon_objetivo + 180) % 360) - 180)))
            puntos_indices.append((area, punto, iy, ix))

        for fecha in fechas:
            comienzo = _fecha_hora(fecha, "04")
            fin = _fecha_hora(fecha, cierre) + timedelta(days=1)
            if min(validas) > comienzo:
                errores[fecha] = "el ciclo no llega a la hora inicial 04Z"
                continue
            if max(validas) < fin:
                errores[fecha] = f"el ciclo no llega al cierre {fin:%Y-%m-%d %HZ}"
                continue

            if tipo_variable == "gust":
                indices = [i for i, hora in enumerate(validas) if comienzo <= hora <= fin]
                if not indices:
                    errores[fecha] = "no hay horas del pronóstico en el período"
                    continue
                for area, punto, iy, ix in puntos_indices:
                    serie = np.ma.asarray(variable[indices, iy, ix], dtype=float)
                    valores = np.asarray(serie.filled(np.nan), dtype=float)
                    valor = float(np.nanmax(valores)) if np.isfinite(valores).any() else np.nan
                    if np.isfinite(valor):
                        valor *= FACTORES_VIENTO[unidad]
                        resultados[fecha].setdefault(area, {})[punto] = valor
                    else:
                        resultados[fecha].setdefault(area, {})[punto] = None
            elif tipo_variable == "tp":
                # tp está acumulada desde el inicio del ciclo (kg m-2 = mm).
                # Se resta el acumulado previo a 04Z para obtener el total diario.
                indices_base = [i for i, hora in enumerate(validas) if hora <= comienzo]
                indices_fin = [i for i, hora in enumerate(validas) if hora == fin]
                if not indices_base or not indices_fin:
                    errores[fecha] = "el NetCDF no tiene los horarios necesarios para el acumulado diario"
                    continue
                i_base, i_fin = indices_base[-1], indices_fin[-1]
                for area, punto, iy, ix in puntos_indices:
                    valores = np.ma.asarray(variable[[i_base, i_fin], iy, ix], dtype=float).filled(np.nan)
                    if np.isfinite(valores).all():
                        total = max(0.0, float(valores[1] - valores[0]))
                        resultados[fecha].setdefault(area, {})[punto] = total
                    else:
                        resultados[fecha].setdefault(area, {})[punto] = None
            else:
                if formato_especial:
                    horas_objetivo = (
                        _fecha_hora(fecha, "12"),
                        _fecha_hora(fecha, "00") + timedelta(days=1),
                    )
                    indices_especiales = []
                    for hora_objetivo in horas_objetivo:
                        encontrados = [i for i, hora in enumerate(validas) if hora == hora_objetivo]
                        if not encontrados:
                            indices_especiales = []
                            break
                        indices_especiales.append(encontrados[0])
                    if not indices_especiales:
                        errores[fecha] = "no están disponibles ambas horas del formato especial 12Z / 00Z"
                        continue
                    for area, punto, iy, ix in puntos_indices:
                        valores = np.ma.asarray(variable[indices_especiales, iy, ix], dtype=float).filled(np.nan)
                        par = tuple(float(v) for v in valores) if np.isfinite(valores).all() else None
                        resultados[fecha].setdefault(area, {})[punto] = par
                else:
                    indices = [i for i, hora in enumerate(validas) if comienzo <= hora <= fin]
                    if not indices:
                        errores[fecha] = "no hay horas del pronóstico en el período"
                        continue
                    for area, punto, iy, ix in puntos_indices:
                        serie = np.ma.asarray(variable[indices, iy, ix], dtype=float).filled(np.nan)
                        valores = serie[np.isfinite(serie)]
                        par = (float(np.min(valores)), float(np.max(valores))) \
                            if valores.size else None
                        resultados[fecha].setdefault(area, {})[punto] = par

    return {"valores": resultados, "errores": errores, "variable": nombre_variable}


@st.cache_data(show_spinner="Leyendo la serie del punto…")
def calcular_serie_temporal(ruta: str, mtime: float, tipo_variable: str,
                            unidad: str, lat: float, lon: float,
                            aproximar_centenas: bool = True) -> list[dict]:
    del mtime  # el valor también forma parte de la clave de caché
    with Dataset(ruta, "r") as ds:
        inicio_ciclo = _inicio_ciclo(ds)
        leads = np.asarray(ds.variables["forecast_hour"][:], dtype=float)
        validas = [inicio_ciclo + timedelta(hours=float(lead)) for lead in leads]
        indices = list(range(len(validas)))
        objetivo = tipo_variable
        candidatas = [
            variable for nombre, variable in ds.variables.items()
            if str(getattr(variable, "GRIB_shortName", "")).casefold() == objetivo
            or nombre.casefold().startswith(
                ("gust",) if objetivo == "gust" else ("tp_", "tp") if objetivo == "tp" else ("gh_iso0",)
            )
        ]
        if not candidatas:
            raise ValueError(f"No se encontró la variable {objetivo} en el NetCDF.")
        variable = candidatas[0]
        latitudes = np.asarray(ds.variables["latitude"][:], dtype=float)
        longitudes = np.asarray(ds.variables["longitude"][:], dtype=float)
        iy = int(np.nanargmin(np.abs(latitudes - lat)))
        longitudes = ((longitudes + 180) % 360) - 180
        lon_objetivo = ((lon + 180) % 360) - 180
        ix = int(np.nanargmin(np.abs(((longitudes - lon_objetivo + 180) % 360) - 180)))
        valores = np.ma.asarray(variable[indices, iy, ix], dtype=float).filled(np.nan)

        if tipo_variable == "gust":
            serie = [
                {"Fecha": validas[indice], "Valor": int(round(float(valor) * FACTORES_VIENTO[unidad]))}
                for indice, valor in zip(indices, valores) if np.isfinite(valor)
            ]
        elif tipo_variable == "tp":
            serie = [
                {"Fecha": validas[indice], "Valor": int(round(float(valor)))}
                for indice, valor in zip(indices, valores) if np.isfinite(valor)
            ]
        else:
            serie = [
                {"Fecha": validas[indice], "Valor": _formatea_isoterma(float(valor), aproximar_centenas)}
                for indice, valor in zip(indices, valores) if np.isfinite(valor)
            ]
    return serie


def _controles_tablas(ciclos: list[tuple[str, Path]]) -> tuple[str, str, str, str, bool, bool]:
    ciclo_labels = {clave: f"{clave[:8]} · {clave[9:]}Z" for clave, _ in ciclos}
    opciones_ciclo = [clave for clave, _ in ciclos]
    ciclo_default = st.session_state.get("tablas_ciclo")
    if ciclo_default not in opciones_ciclo:
        ciclo_default = opciones_ciclo[0]
    if st.session_state.get("tablas_ciclo") not in opciones_ciclo:
        st.session_state["tablas_ciclo"] = ciclo_default
    if "tablas_variable" not in st.session_state:
        st.session_state["tablas_variable"] = "Racha de viento"
    if "tablas_cierre" not in st.session_state:
        st.session_state["tablas_cierre"] = cargar_cierre_global()

    col_ciclo, col_cierre, col_variable, col_unidad, col_formato, col_guardar, col_leyenda = st.columns(
        [2, 1, 2.2, 1, 1.35, 1.25, 1]
    )
    with col_ciclo:
        ciclo = st.selectbox("Ciclo", opciones_ciclo, format_func=lambda v: ciclo_labels[v], key="tablas_ciclo")
    with col_cierre:
        cierre = st.selectbox("Cierre UTC", HORAS_CIERRE,
                              format_func=lambda v: f"{v}Z", key="tablas_cierre")
    with col_variable:
        variable = st.selectbox("Variable", tuple(VARIABLES), key="tablas_variable")
    tipo_variable = VARIABLES[variable]
    opciones_unidad = UNIDADES_VIENTO if tipo_variable == "gust" else ("mm",) if tipo_variable == "tp" else ("m",)
    key_unidad = ("tablas_unidad_viento" if tipo_variable == "gust"
                  else "tablas_unidad_precipitacion" if tipo_variable == "tp" else "tablas_unidad_isoterma")
    if key_unidad not in st.session_state:
        st.session_state[key_unidad] = "km/h" if tipo_variable == "gust" else "mm" if tipo_variable == "tp" else "m"
    with col_unidad:
        unidad = st.selectbox("Unidad", opciones_unidad, key=key_unidad)
    with col_formato:
        if tipo_variable == "gh_iso0":
            formato_especial = st.toggle(
                "Formato especial 12Z / 00Z", key="tablas_formato_especial",
                help="Muestra las alturas de isoterma 0 a las 12Z del día y 00Z del día siguiente.",
            )
            aproximar_centenas = st.toggle(
                "Aproximar a centenas", value=True, key="tablas_aproximar_centenas",
                help="Redondea los valores de isoterma 0 a la centena de metros más cercana.",
            )
        else:
            formato_especial = False
            aproximar_centenas = False
            st.empty()
    with col_guardar:
        st.markdown("<div style='height:1.75rem'></div>", unsafe_allow_html=True)
        if st.button("Guardar cierre", use_container_width=True):
            try:
                guardar_cierre_global(cierre)
                st.success(f"Cierre {cierre}Z guardado.")
            except OSError as exc:
                st.error(f"No se pudo guardar el cierre: {exc}")
    with col_leyenda:
        _mostrar_leyenda(tipo_variable, unidad)
    return ciclo, cierre, variable, unidad, formato_especial, aproximar_centenas


def mostrar_tablas() -> None:
    ciclos = listar_ciclos()
    if not ciclos:
        st.warning(f"No se encontraron archivos *gust*.nc en `{DIR_NC}`.")
        return

    ciclo, cierre, variable, unidad, formato_especial, aproximar_centenas = _controles_tablas(ciclos)
    tipo_variable = VARIABLES[variable]
    ruta = ruta_variable(ciclo, tipo_variable)
    st.caption("El día operativo va desde las 04Z de la fecha hasta la hora de cierre del día siguiente.")

    if st.button("Guardar histórico del ciclo", help="Guarda todas las horas disponibles de racha, precipitación e isoterma 0 para cada punto."):
        try:
            with st.spinner("Extrayendo las series temporales del ciclo…"):
                archivo, cantidad, faltantes = guardar_historico_ciclo(ciclo, cargar_puntos())
            st.success(f"Histórico guardado: {archivo} · {cantidad:,} registros.")
            if faltantes:
                st.warning("No se encontraron archivos para: " + ", ".join(faltantes) + ". Se guardaron las variables disponibles.")
        except Exception as exc:
            st.error(f"No se pudo guardar el histórico: {exc}")

    if ruta is None:
        if tipo_variable == "tp":
            st.warning(f"No se encontró precipitación total (*tp_sfc*, incluido msg597) para el ciclo {ciclo}.")
        else:
            st.warning(f"No se encontró el archivo {variable} para el ciclo {ciclo}.")
        return

    mtime = ruta.stat().st_mtime
    try:
        fechas = tuple(fechas_disponibles(str(ruta), mtime))
        if not fechas:
            st.info("Este ciclo no cubre un día completo desde 04Z hasta 03Z del día siguiente.")
            return
        puntos = tuple((p["area"], p["punto"], p["lat"], p["lon"]) for p in cargar_puntos())
        datos = calcular_maximos(
            str(ruta), mtime, fechas, cierre, tipo_variable, unidad, formato_especial, puntos
        )
        config_colores = cargar_rangos(tipo_variable) if tipo_variable in ARCHIVOS_COLORES else None
        if tipo_variable == "gust":
            config_colores = rangos_viento_en_unidad(config_colores, unidad)
    except Exception as exc:
        st.error(f"No se pudieron leer los datos: {exc}")
        return

    fechas_columna = {
        fecha: datetime.strptime(fecha, "%Y%m%d").strftime("%d-%m-%Y")
        for fecha in fechas
    }
    areas = list(dict.fromkeys(area for area, _, _, _ in puntos))
    resumen = []
    detalle_por_area = {}
    for area in areas:
        fila_area = {"Área": area}
        detalle = []
        for area_punto, punto, _, _ in puntos:
            if area_punto != area:
                continue
            fila_punto = {"Punto": punto}
            for fecha in fechas:
                etiqueta = fechas_columna[fecha]
                valor = datos["valores"].get(fecha, {}).get(area, {}).get(punto)
                if fecha in datos["errores"]:
                    valor = None
                if tipo_variable == "gh_iso0" and valor is not None:
                    valor = (f"{_formatea_isoterma(valor[0], aproximar_centenas)} / "
                             f"{_formatea_isoterma(valor[1], aproximar_centenas)}")
                fila_punto[etiqueta] = valor
            detalle.append(fila_punto)
        for fecha in fechas:
            etiqueta = fechas_columna[fecha]
            valores_area = list(datos["valores"].get(fecha, {}).get(area, {}).values())
            valores_area = [valor for valor in valores_area if valor is not None]
            if fecha in datos["errores"] or not valores_area:
                fila_area[etiqueta] = None
            elif tipo_variable == "gh_iso0":
                if formato_especial:
                    primero = _formatea_isoterma(max(valor[0] for valor in valores_area), aproximar_centenas)
                    segundo = _formatea_isoterma(max(valor[1] for valor in valores_area), aproximar_centenas)
                else:
                    primero = _formatea_isoterma(min(valor[0] for valor in valores_area), aproximar_centenas)
                    segundo = _formatea_isoterma(max(valor[1] for valor in valores_area), aproximar_centenas)
                fila_area[etiqueta] = f"{primero} / {segundo}"
            else:
                fila_area[etiqueta] = max(valores_area)
        resumen.append(fila_area)
        detalle_por_area[area] = detalle

    titulo_tabla = "Isoterma 0 por área" if tipo_variable == "gh_iso0" else "Máximo por área"
    st.subheader(f"{titulo_tabla} · selecciona una fila para ver los puntos")
    if tipo_variable == "gh_iso0":
        st.caption(
            "Formato especial: valores 12Z del día / 00Z del día siguiente."
            if formato_especial else "Cada celda muestra el mínimo / máximo del período diario."
        )
    evento_area = st.dataframe(
        _tabla_con_colores(resumen, tipo_variable, config_colores),
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key=f"tabla_areas_{ciclo}_{tipo_variable}",
    )
    filas_area = list(evento_area.selection.rows)
    if filas_area:
        indice_area = filas_area[0]
        area = resumen[indice_area]["Área"]
        st.markdown(f"#### {area} · detalle de puntos")
        evento_punto = st.dataframe(
            _tabla_con_colores(detalle_por_area[area], tipo_variable, config_colores,
                               area_detalle=area),
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key=f"tabla_puntos_{ciclo}_{tipo_variable}_{area}",
        )
        filas_punto = list(evento_punto.selection.rows)
        if filas_punto:
            seleccion = detalle_por_area[area][filas_punto[0]]
            punto = seleccion["Punto"]
            coord_punto = next(p for p in puntos if p[0] == area and p[1] == punto)
            try:
                serie = calcular_serie_temporal(
                    str(ruta), mtime, tipo_variable, unidad,
                    coord_punto[2], coord_punto[3], aproximar_centenas,
                )
                st.markdown(f"#### Serie temporal completa · {punto}")
                if serie:
                    st.line_chart(pd.DataFrame(serie).set_index("Fecha"), y="Valor", y_label=unidad, width="stretch")
                    descripciones = {
                        "gust": "Rachas en todos los horarios de pronóstico disponibles.",
                        "tp": "Precipitación acumulada desde el inicio del ciclo, en todos los horarios disponibles.",
                        "gh_iso0": "Altura de la isoterma 0 en todos los horarios de pronóstico disponibles.",
                    }
                    st.caption(descripciones[tipo_variable])
                else:
                    st.info("No hay valores disponibles para graficar en este punto.")
            except Exception as exc:
                st.error(f"No se pudo calcular la serie temporal: {exc}")

    if datos["errores"]:
        avisos = [f"{fechas_columna[fecha]}: {error}" for fecha, error in datos["errores"].items()]
        st.warning("No se pudo calcular el período completo para: " + "; ".join(avisos))
    st.caption(f"Variable: {variable} · unidades {unidad} · archivo {ruta.name}")
