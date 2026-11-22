"""Comprueba que se pueden importar las dependencias del workflow y muestra la causa real si no."""
import importlib
import sys
import sysconfig

print(f"Python {sys.version.split()[0]} ({sysconfig.get_platform()})")
fallos = []
for nombre in ("numpy", "netCDF4", "pygrib", "pandas", "pyarrow", "openpyxl", "requests"):
    try:
        modulo = importlib.import_module(nombre)
        print(f"OK     {nombre} {getattr(modulo, '__version__', '')}")
    except Exception as exc:   # cualquier fallo de importación (no solo ImportError)
        print(f"FALLA  {nombre}: {type(exc).__name__}: {exc}")
        fallos.append(nombre)
if fallos:
    print(f"::error::No se pueden importar: {', '.join(fallos)}")
    sys.exit(1)
