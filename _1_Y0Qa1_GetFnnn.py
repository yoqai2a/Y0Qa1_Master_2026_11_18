#!/usr/bin/env python3
"""Iniciador de la descarga de archivos fNNN (GFS / NOMADS) del proyecto Y0Qa1.

Estructura:
    Y0Qa1/
    ├── _1_Y0Qa1_GetFnnn.py                          <- este archivo
    ├── _1_GetFnnn/
    │   ├── __Configuracion_Fnnn.toml        <- configuración
    │   ├── Main_Fnnn.py                     <- orquestador
    │   ├── configuracion.py  conjuntos.py  nomads.py
    │   └── ciclos.py  descarga.py  ci.py  utilidades.py
    └── ___Data/___Fnnn/AAAAMMDD/HH/         <- GRIB descargados

Uso (desde cualquier carpeta):
    python _1_Y0Qa1_GetFnnn.py                        # interactivo
    python _1_Y0Qa1_GetFnnn.py --sin-preguntas        # último ciclo disponible
    python _1_Y0Qa1_GetFnnn.py --fecha 20261104 --ciclo 12
    python _1_Y0Qa1_GetFnnn.py --conjunto XyGrib --simular

Dependencias: pip install -r requirements.txt
"""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))

from _1_GetFnnn.Main_Fnnn import main  # noqa: E402

if __name__ == "__main__":
    print("Y0Qa1: iniciando _1_GetFnnn/Main_Fnnn.py", flush=True)
    raise SystemExit(main())
