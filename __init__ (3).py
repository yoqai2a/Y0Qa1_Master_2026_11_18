"""Pestaña Corte temporal: perfil vertical (presión) a lo largo del tiempo para cada punto.

Todo lo de esta pestaña vive en esta carpeta:
    configuracion/   capas_nc.json, variables.json, puntos.json, almacenamiento.json
    config.py        lectura y validación de la configuración
    datos.py         lectura de las capas NetCDF y del respaldo de perfiles
    calculo.py       campos derivados (rapidez, barbas) y conversión de unidades
    grafico.py       figura tiempo x presión (matplotlib)
    interfaz.py      pantalla de Streamlit
"""
