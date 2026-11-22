"""Pestaña Tablas: resúmenes diarios por área, detalle por punto, serie temporal y exportación.

Todo lo de esta pestaña vive en esta carpeta:
    configuracion/     Puntos.json, cierres_tablas.json y las paletas rangos_*.json
    variables.py       definición declarativa de las 8 variables (etiquetas, unidades, factores)
    datos.py           ciclos, NetCDF, histórico y cierres (sin Streamlit)
    calculo.py         períodos diarios, máximos por área y series temporales (con caché)
    estilos.py         paletas, leyendas y estilo de las tablas
    pdf.py             PDF imprimible
    interfaz.py        pantalla de Streamlit (mostrar_tablas)
    archivar_ciclo.py  crea el histórico de un ciclo (lo usa el workflow)

Este archivo no importa Streamlit a propósito: archivar_ciclo.py se ejecuta en GitHub Actions sin él.
"""
