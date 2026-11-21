"""Crea el respaldo de perfiles de la pestaña Corte temporal a partir de las capas NetCDF.

Uso:
    python _0_Visor/archivar_corte.py --fecha 20261119 --ciclo 12      # un ciclo (lo usa el workflow)
    python _0_Visor/archivar_corte.py --todos                          # todos los ciclos con NetCDF

Con ``--todos`` se rehacen los respaldos con los puntos actuales de
``corte_temporal/configuracion/puntos.json``: es lo que conviene ejecutar después de cambiar los
puntos (requiere que las capas NetCDF de esos ciclos estén en ___Data/___NC). No requiere Streamlit.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import datos_ciclos as dc  # noqa: E402
from _Comun.registro import configurar as configurar_logging  # noqa: E402
from corte_temporal import datos as dt  # noqa: E402
from corte_temporal.config import ARCHIVO_PUNTOS, cargar_config  # noqa: E402
from variables_meteo import CICLOS_VALIDOS  # noqa: E402

log = logging.getLogger(__name__)


def _ciclos_con_netcdf() -> list[str]:
    ciclos = []
    if dc.DIR_NC.is_dir():
        for carpeta in sorted(dc.DIR_NC.glob("*/*")):
            if carpeta.is_dir() and carpeta.parent.name.isdigit() and carpeta.name in CICLOS_VALIDOS:
                clave = f"{carpeta.parent.name}_{carpeta.name}"
                if dt.indice_capas_nc(clave):
                    ciclos.append(clave)
    return ciclos


def main() -> int:
    configurar_logging()
    parser = argparse.ArgumentParser(description="Crea el respaldo de perfiles del Corte temporal.")
    parser.add_argument("--fecha", help="Fecha del ciclo (AAAAMMDD)")
    parser.add_argument("--ciclo", choices=CICLOS_VALIDOS)
    parser.add_argument("--todos", action="store_true", help="Rehace todos los ciclos con capas NetCDF")
    args = parser.parse_args()
    if not args.todos and not (args.fecha and args.ciclo):
        parser.error("indica --fecha y --ciclo, o bien --todos")

    cfg = cargar_config()
    puntos = dc.cargar_puntos(ARCHIVO_PUNTOS)
    claves = _ciclos_con_netcdf() if args.todos else [f"{args.fecha}_{args.ciclo}"]
    if not claves:
        log.info("No hay ciclos con capas NetCDF en %s.", dc.DIR_NC)
        return 0
    hubo_faltantes = False
    for clave in claves:
        try:
            archivo, filas, faltantes = dt.guardar_perfiles_ciclo(clave, cfg, puntos)
        except FileNotFoundError as exc:
            raise SystemExit(str(exc)) from exc
        log.info(f"{clave}Z: {filas} filas de {len(puntos)} puntos en {archivo}.")
        if faltantes:
            hubo_faltantes = True
            log.warning(f"AVISO: {clave}Z no tiene {len(faltantes)} capa(s): {', '.join(faltantes[:6])}"
                        f"{'…' if len(faltantes) > 6 else ''}")
    if hubo_faltantes and not args.todos:
        raise SystemExit("Faltan capas NetCDF requeridas para el Corte temporal.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
