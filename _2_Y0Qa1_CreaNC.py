#!/usr/bin/env python3
"""Iniciador de la creación de NetCDF (.nc) del proyecto Y0Qa1.

Lee los fNNN que deja _1_Y0Qa1_GetFnnn.py en ___Data/___Fnnn y escribe en ___Data/___NC.

Estructura:
    Y0Qa1/
    ├── _2_Y0Qa1_CreaNC.py                          <- este archivo
    ├── _2_CreaNC/
    │   ├── __Configuracion_NC.toml          <- entrada/salida, agrupación, compresión
    │   ├── __Variables_NC.toml              <- qué variables se escriben
    │   ├── Main_NC.py                       <- orquestador
    │   └── configuracion.py variables.py entrada.py grib.py plan.py
    │       escritor.py conversion.py salida.py utilidades.py
    └── ___Data/___NC/AAAAMMDD/HH/           <- .nc + Indice.json  (y ___NC/ultimo.json)

Uso (desde cualquier carpeta):
    python _2_Y0Qa1_CreaNC.py                        # último ciclo descargado
    python _2_Y0Qa1_CreaNC.py --fecha 20261106 --ciclo 12
    python _2_Y0Qa1_CreaNC.py --agrupacion variable --procesos 4
    python _2_Y0Qa1_CreaNC.py --simular
    python _2_Y0Qa1_CreaNC.py --inventario ___Data/___Fnnn/20261106/12/gfs.t12z.pgrb2.0p25.f012

Dependencias: pip install -r requirements.txt
"""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))

from _2_CreaNC.Main_NC import main  # noqa: E402

if __name__ == "__main__":
    print("Y0Qa1: iniciando _2_CreaNC/Main_NC.py", flush=True)
    raise SystemExit(main())
