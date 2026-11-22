"""Crea el histórico comprimido que consumen las tablas del visor."""
from __future__ import annotations

import argparse

from tablas import guardar_historico_ciclo, cargar_puntos


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fecha", required=True, help="Fecha del ciclo en formato AAAAMMDD")
    parser.add_argument("--ciclo", required=True, choices=("00", "06", "12", "18"))
    args = parser.parse_args()
    clave = f"{args.fecha}_{args.ciclo}"
    archivo, registros, faltantes = guardar_historico_ciclo(clave, cargar_puntos())
    if faltantes:
        raise SystemExit("Faltan NetCDF requeridos para el histórico: " + ", ".join(faltantes))
    print(f"Histórico guardado en {archivo}: {registros} registros.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
