"""Imprime los pathspec de Git que excluyen del commit las capas NetCDF del Corte temporal.

Si ``publicar_nc_en_git`` es true en
``_0_Visor/corte_temporal/configuracion/almacenamiento.json`` no imprime nada (se publican todas).
Ante cualquier duda (archivo ausente o dañado) se excluyen: es la opción que protege el repositorio.
"""
import json
import re
from pathlib import Path

CONFIG = Path("_0_Visor/corte_temporal/configuracion")


def _leer(nombre: str) -> dict:
    try:
        datos = json.loads((CONFIG / nombre).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    return datos if isinstance(datos, dict) else {}


if _leer("almacenamiento.json").get("publicar_nc_en_git") is not True:
    archivos = _leer("capas_nc.json").get("archivos", {})
    prefijos = sorted({m.group(1) for nombre in archivos if (m := re.fullmatch(r"([A-Za-z0-9]+)_\d+hPa", nombre))})
    for prefijo in prefijos:
        print(f":(exclude)___Data/___NC/*/*/*_{prefijo}_[0-9]*hPa_msg*.nc")
