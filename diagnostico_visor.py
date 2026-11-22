"""Diagnóstico del visor: revisa archivos, librerías, importaciones y datos, y escribe un informe.

Uso (desde la carpeta del proyecto, la que contiene Y0Qa1_Visor.py):
    python diagnostico_visor.py

Deja el informe en ``diagnostico_visor.txt`` (ábrelo con el Bloc de notas, copia todo y pégalo donde
necesites ayuda). No modifica nada: solo lee.
"""
from __future__ import annotations

import importlib
import io
import logging
import platform
import sys
import time
import traceback
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
VISOR = RAIZ / "_0_Visor"
SALIDA = RAIZ / "diagnostico_visor.txt"
sys.path.insert(0, str(VISOR))
sys.path.insert(0, str(RAIZ))
logging.disable(logging.CRITICAL)          # silencia los avisos internos de Streamlit en modo script

_informe = io.StringIO()


def escribir(texto: str = "") -> None:
    print(texto)
    _informe.write(texto + "\n")


def titulo(texto: str) -> None:
    escribir(f"\n=== {texto} ===")


def causa(exc: BaseException) -> str:
    """Última línea útil del error, más el archivo y la línea donde ocurrió."""
    marco = traceback.extract_tb(exc.__traceback__)[-1:] or []
    donde = f" [{Path(marco[0].filename).name}:{marco[0].lineno}]" if marco else ""
    return f"{type(exc).__name__}: {exc}{donde}"


# --------------------------------------------------------------------------- 1. entorno
def entorno() -> None:
    titulo("1. Entorno")
    escribir(f"Python {platform.python_version()} · {platform.platform()}")
    escribir(f"Proyecto: {RAIZ}")
    for nombre in ("streamlit", "pandas", "numpy", "netCDF4", "openpyxl", "pyarrow", "fpdf", "matplotlib", "jinja2",
                   "requests"):
        try:
            modulo = importlib.import_module(nombre)
            escribir(f"  OK     {nombre} {getattr(modulo, '__version__', '')}")
        except Exception as exc:
            escribir(f"  FALTA  {nombre}  ->  {causa(exc)}")


# --------------------------------------------------------------------------- 2. archivos
REQUERIDOS = [
    "Y0Qa1_Visor.py", "_Comun/__init__.py", "_Comun/malla_nc.py", "_Comun/control_ciclos.py", "_Comun/registro.py",
    "_0_Visor/Y0Qa1_Panel.py", "_0_Visor/accounts.py", "_0_Visor/errores.py", "_0_Visor/limitador.py",
    "_0_Visor/tablas/__init__.py", "_0_Visor/tablas/interfaz.py", "_0_Visor/tablas/calculo.py",
    "_0_Visor/tablas/datos.py", "_0_Visor/tablas/estilos.py", "_0_Visor/tablas/pdf.py",
    "_0_Visor/tablas/variables.py", "_0_Visor/tablas/archivar_ciclo.py",
    "_0_Visor/tablas/configuracion/Puntos.json", "_0_Visor/tablas/configuracion/cierres_tablas.json",
    "_0_Visor/tablas/configuracion/rangos_viento.json", "_0_Visor/tablas/configuracion/rangos_precipitacion.json",
    "_0_Visor/tablas/configuracion/rangos_cape.json", "_0_Visor/tablas/configuracion/rangos_temperatura.json",
    "_0_Visor/tablas/configuracion/rangos_base_nubes.json", "_0_Visor/tablas/configuracion/rangos_visibilidad.json",
    "_0_Visor/corte_temporal/__init__.py", "_0_Visor/corte_temporal/configuracion/variables.json",
    "_0_Visor/corte_temporal/configuracion/capas_nc.json", "_0_Visor/corte_temporal/configuracion/puntos.json",
]
OBSOLETOS = [   # de versiones anteriores: si siguen ahí pueden mezclarse con los nuevos
    "_0_Visor/tablas.py", "_0_Visor/calculo_tablas.py", "_0_Visor/estilos_tablas.py", "_0_Visor/pdf_tablas.py",
    "_0_Visor/variables_meteo.py", "_0_Visor/datos_ciclos.py", "_0_Visor/archivar_ciclo.py", "_0_Visor/Puntos.json",
    "_0_Visor/cierres_tablas.json", "_0_Visor/rangos_viento.json", "_0_Visor/requirements_panel.txt",
    "YoQa1_Visor.py", "_1_YoQai_GetFnnn.py", "_2_YoQai_CreaNC.py",
]


def archivos() -> None:
    titulo("2. Archivos")
    faltan = [r for r in REQUERIDOS if not (RAIZ / r).is_file()]
    escribir(f"Requeridos: {len(REQUERIDOS) - len(faltan)} de {len(REQUERIDOS)} presentes.")
    for r in faltan:
        escribir(f"  FALTA    {r}")
    sobran = [o for o in OBSOLETOS if (RAIZ / o).exists()]
    for o in sobran:
        escribir(f"  OBSOLETO {o}   (de una versión anterior: bórralo)")
    if not faltan and not sobran:
        escribir("  Todo en orden.")


# --------------------------------------------------------------------------- 3. importaciones
MODULOS = ["_Comun.malla_nc", "_Comun.control_ciclos", "tablas", "tablas.variables", "tablas.datos",
           "tablas.calculo", "tablas.estilos", "tablas.interfaz", "tablas.pdf", "corte_temporal.config",
           "corte_temporal.datos", "corte_temporal.calculo", "corte_temporal.grafico", "corte_temporal.interfaz",
           "accounts", "errores"]


def importaciones() -> None:
    titulo("3. Importación de módulos")
    for nombre in MODULOS:
        try:
            modulo = importlib.import_module(nombre)
            origen = getattr(modulo, "__file__", None)
            marca = ""
            if nombre == "tablas" and origen and not str(origen).replace("\\", "/").endswith("tablas/__init__.py"):
                marca = "   <-- OJO: no es el paquete tablas/ (hay un tablas.py antiguo que lo tapa)"
            escribir(f"  OK     {nombre}{marca}")
        except Exception as exc:
            escribir(f"  FALLA  {nombre}  ->  {causa(exc)}")


# --------------------------------------------------------------------------- 4. configuración
def configuracion() -> None:
    titulo("4. Configuración de Tablas")
    try:
        from tablas import datos, estilos
        from tablas.variables import VARIABLES_METEO
        puntos = datos.cargar_puntos()
        escribir(f"  OK     Puntos.json: {len(puntos)} puntos en {len({p.area for p in puntos})} áreas")
        for clave, definicion in VARIABLES_METEO.items():
            if definicion.archivo_rangos:
                try:
                    estilos.cargar_rangos(clave)
                    escribir(f"  OK     paleta de {clave} ({definicion.archivo_rangos})")
                except Exception as exc:
                    escribir(f"  FALLA  paleta de {clave} ({definicion.archivo_rangos})  ->  {causa(exc)}")
    except Exception as exc:
        escribir(f"  FALLA  {causa(exc)}")


# --------------------------------------------------------------------------- 5. datos
def datos_tablas() -> None:
    titulo("5. Datos de Tablas (el ciclo más reciente)")
    try:
        from tablas import calculo as ct
        from tablas import datos
        from tablas.variables import VARIABLES_METEO
        escribir(f"  Carpeta de NetCDF:   {datos.malla.DIR_NC}  (existe: {datos.malla.DIR_NC.is_dir()})")
        escribir(f"  Carpeta de histórico: {datos.DIR_HISTORICO}  (existe: {datos.DIR_HISTORICO.is_dir()})")
        ciclos = datos.listar_ciclos()
        escribir(f"  Ciclos encontrados: {len(ciclos)}" + (f"  ->  {', '.join(c for c, _ in ciclos[:5])}" if ciclos else ""))
        if not ciclos:
            escribir("  No hay NetCDF ni históricos: la pestaña Tablas mostraría el aviso 'No se encontraron...'.")
            return
        clave = ciclos[0][0]
        puntos = datos.cargar_puntos()
        for definicion in VARIABLES_METEO.values():
            ruta = datos.ruta_variable(clave, definicion.clave)
            if ruta is None:
                escribir(f"  SIN ARCHIVO  {definicion.clave}")
                continue
            try:
                inicio = time.perf_counter()
                mtime = ruta.stat().st_mtime
                fechas = tuple(ct.fechas_disponibles(str(ruta), mtime, cierre="12"))
                resultado = ct.calcular_maximos(str(ruta), mtime, fechas, "12", definicion.clave,
                                                definicion.unidad_defecto, False, puntos)
                con_dato = sum(1 for f in resultado["valores"].values() for a in f.values()
                               for v in a.values() if v is not None)
                escribir(f"  OK     {definicion.clave:11s} {ruta.name[:48]}  ({len(fechas)} períodos, "
                         f"{con_dato} valores, {time.perf_counter() - inicio:.1f} s)")
            except Exception as exc:
                escribir(f"  FALLA  {definicion.clave:11s} {ruta.name}  ->  {causa(exc)}")
                escribir("         " + traceback.format_exc().strip().replace("\n", "\n         "))
    except Exception as exc:
        escribir(f"  FALLA  {causa(exc)}")
        escribir(traceback.format_exc())


# --------------------------------------------------------------------------- 6. la pantalla de Tablas
def pantalla_tablas() -> None:
    titulo("6. Pantalla de Tablas (misma ruta que usa el visor)")
    try:
        from streamlit.testing.v1 import AppTest
    except Exception as exc:
        escribir(f"  (omitido: {causa(exc)})")
        return
    guion = (
        "import sys\n"
        f"sys.path.insert(0, {str(VISOR)!r}); sys.path.insert(0, {str(RAIZ)!r})\n"
        "import streamlit as st\n"
        "from tablas.interfaz import mostrar_tablas\n"
        "mostrar_tablas()\n")
    try:
        app = AppTest.from_string(guion, default_timeout=120).run()
        if app.exception:
            for e in app.exception:
                escribir(f"  FALLA  {e.value}")
                escribir("         " + "\n         ".join(str(e.stack_trace).splitlines()[-12:]) if getattr(e, "stack_trace", None) else "")
        else:
            escribir(f"  OK     la pantalla se dibujó: {len(app.dataframe)} tabla(s), {len(app.selectbox)} selector(es)")
            for aviso in list(app.warning) + list(app.error):
                escribir(f"  AVISO  {aviso.value[:300]}")
    except Exception as exc:
        escribir(f"  FALLA  {causa(exc)}")
        escribir(traceback.format_exc())


def main() -> None:
    escribir(f"Diagnóstico del visor Y0Qa1 · {time.strftime('%Y-%m-%d %H:%M:%S')}")
    for paso in (entorno, archivos, importaciones, configuracion, datos_tablas, pantalla_tablas):
        try:
            paso()
        except Exception as exc:               # un fallo del diagnóstico no debe ocultar el resto
            escribir(f"  ERROR interno en {paso.__name__}: {causa(exc)}")
    SALIDA.write_text(_informe.getvalue(), encoding="utf-8")
    print(f"\nInforme guardado en: {SALIDA}\nAbre ese archivo, copia todo su contenido y pégalo en el chat.")


if __name__ == "__main__":
    main()
