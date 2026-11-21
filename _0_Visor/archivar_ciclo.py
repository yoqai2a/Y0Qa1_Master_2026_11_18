"""Crea el histórico de un ciclo (series de todos los puntos y variables) que usan las tablas del visor.

Uso:
    python _0_Visor/archivar_ciclo.py --fecha 20261119 --ciclo 12
    python _0_Visor/archivar_ciclo.py --fecha 20261119 --ciclo 12 --formato csv   # CSV comprimido (anterior)

Los NetCDF del ciclo deben existir en ___Data/___NC. No requiere Streamlit.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _Comun.registro import configurar as configurar_logging  # noqa: E402
from datos_ciclos import FORMATOS_HISTORICO, cargar_puntos, guardar_historico_ciclo  # noqa: E402
from variables_meteo import CICLOS_VALIDOS  # noqa: E402

log = logging.getLogger(__name__)


def main() -> int:
    configurar_logging()
    parser = argparse.ArgumentParser(description="Crea el histórico de un ciclo para el visor.")
    parser.add_argument("--fecha", required=True, help="Fecha del ciclo en formato AAAAMMDD")
    parser.add_argument("--ciclo", required=True, choices=CICLOS_VALIDOS)
    parser.add_argument("--formato", choices=FORMATOS_HISTORICO, default="parquet",
                        help="parquet (por defecto, compacto) o csv (CSV comprimido con gzip)")
    args = parser.parse_args()
    clave = f"{args.fecha}_{args.ciclo}"
    try:
        archivo, registros, faltantes = guardar_historico_ciclo(clave, cargar_puntos(), args.formato)
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc
    if faltantes:
        raise SystemExit("Faltan NetCDF requeridos para el histórico: " + ", ".join(faltantes))
    log.info(f"Histórico guardado en {archivo}: {registros} registros.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
