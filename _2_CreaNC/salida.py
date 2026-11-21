"""Índice para el visor, puntero al último ciclo y limpieza de ciclos antiguos."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from _Comun.control_ciclos import escribir_control as _escribir_control_xlsx
from _Comun.control_ciclos import leer_ciclos_o_respaldar

from .conversion import ResultadoConversion

NOMBRE_INDICE = "Indice.json"
NOMBRE_ULTIMO = "ultimo.json"
NOMBRE_CONTROL = "control.xlsx"
_RE_FECHA = re.compile(r"\d{8}")


def _escribir_json(ruta: Path, datos: dict) -> None:
    temporal = ruta.with_name(ruta.name + ".part")
    temporal.write_text(json.dumps(datos, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(temporal, ruta)


def escribir_indice(res: ResultadoConversion, directorio: Path, agrupacion: str) -> Path:
    """Indice.json: qué hay en cada archivo, para que el visor baje solo lo que muestra."""
    lat, lon = res.lat1d, res.lon1d
    todas = set(res.leads)
    archivos, variables = [], []
    for info in sorted(res.archivos, key=lambda i: i.ruta.name):
        archivos.append({"archivo": info.ruta.name, "bytes": info.bytes,
                         "variables": [c.nombre for c in info.capas if info.horas_con_datos.get(c.nombre)]})
        for c in info.capas:
            horas = info.horas_con_datos.get(c.nombre, [])
            if not horas:                       # variable vacía: no se ofrece al visor
                continue
            entrada = {
                "nombre": c.nombre, "archivo": info.ruta.name, "grupo": c.grupo,
                "shortName": c.short_name, "long_name": c.long_name, "unidades": c.unidades,
                "tipoNivel": c.tipo_nivel, "nivel": c.nivel, "stepType": c.step_type,
            }
            if c.top is not None:
                entrada["topLevel"] = c.top
            if c.bottom is not None:
                entrada["bottomLevel"] = c.bottom
            if c.nombre in info.minimos:
                entrada["min"] = info.minimos[c.nombre]
                entrada["max"] = info.maximos[c.nombre]
            sin_datos = sorted(todas - set(horas))
            if sin_datos:
                entrada["sin_datos_en"] = sin_datos
            variables.append(entrada)
    indice = {
        "version": 1,
        "modelo": "GFS",
        "fecha": res.fecha,
        "ciclo": res.ciclo,
        "creado_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "agrupacion": agrupacion,
        "horas": res.leads,
        "malla": {
            "ny": len(lat), "nx": len(lon),
            "lat_primera": float(lat[0]), "lat_ultima": float(lat[-1]),
            "lon_primera": float(lon[0]), "lon_ultima": float(lon[-1]),
        },
        "archivos": archivos,
        "variables": variables,
        "ausentes": res.ausentes_siempre,
    }
    ruta = directorio / NOMBRE_INDICE
    _escribir_json(ruta, indice)
    return ruta


def ciclos_disponibles(raiz_salida: Path) -> list[str]:
    """['AAAAMMDD/HH', ...] con Indice.json, del más reciente al más antiguo."""
    if not raiz_salida.exists():
        return []
    return sorted(
        (f"{dia.name}/{ciclo.name}"
         for dia in raiz_salida.iterdir() if dia.is_dir() and _RE_FECHA.fullmatch(dia.name)
         for ciclo in dia.iterdir() if ciclo.is_dir() and (ciclo / NOMBRE_INDICE).is_file()),
        reverse=True,
    )


def escribir_ultimo(raiz_salida: Path, res: ResultadoConversion) -> Path:
    """ultimo.json: el visor lo consulta para saber qué ciclo cargar y cuáles hay."""
    ruta = raiz_salida / NOMBRE_ULTIMO
    ciclos = sorted(set(ciclos_disponibles(raiz_salida)) | {f"{res.fecha}/{res.ciclo}"}, reverse=True)
    fecha, hora = ciclos[0].split("/")          # el más reciente disponible, no el último procesado
    _escribir_json(ruta, {
        "fecha": fecha, "ciclo": hora,
        "indice": f"{ciclos[0]}/{NOMBRE_INDICE}",
        "ciclos": ciclos,
        "creado_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    return ruta


def escribir_control(raiz_datos: Path, res: ResultadoConversion) -> Path:
    """Registro matricial: fecha | 00 | 06 | 12 | 18 (ver ``_Comun.control_ciclos``)."""
    ruta = raiz_datos / NOMBRE_CONTROL
    # Si el control existente está dañado se guarda una copia ".corrupto" en vez de perder el historial.
    ciclos = leer_ciclos_o_respaldar(ruta)
    # Migra el control JSON anterior si existe, conservando sus ciclos ya creados.
    anterior = raiz_datos / "Control_NC.json"
    if anterior.is_file():
        try:
            datos = json.loads(anterior.read_text(encoding="utf-8"))
            for clave, entrada in datos.get("ciclos", {}).items():
                if entrada.get("estado") == "creado":
                    fecha, ciclo = clave.split("/", 1)
                    ciclos.add((fecha, ciclo))
        except (OSError, ValueError, AttributeError):
            pass
    ciclos.add((res.fecha, res.ciclo))
    return _escribir_control_xlsx(ruta, ciclos)


def limpiar_ciclos(raiz_salida: Path, conservar: int, proteger: tuple[str, str] | None = None) -> int:
    """Conserva los `conservar` ciclos más recientes y borra los demás.

    Solo elimina lo que genera este programa (.nc, Indice.json y temporales) y
    las carpetas que queden vacías; cualquier otro archivo se respeta. El ciclo
    `proteger` (el recién creado) nunca se borra, aunque sea antiguo.
    """
    if not raiz_salida.exists():
        return 0
    ciclos = sorted(
        (dia.name, ciclo.name, ciclo)
        for dia in raiz_salida.iterdir() if dia.is_dir() and _RE_FECHA.fullmatch(dia.name)
        for ciclo in dia.iterdir() if ciclo.is_dir() and ciclo.name.isdigit()
    )
    sobrantes = ciclos[:-conservar] if len(ciclos) > conservar else []
    borrados = 0
    for fecha, hora, carpeta in sobrantes:
        if (fecha, hora) == proteger:
            continue
        for ruta in carpeta.iterdir():
            if ruta.is_file() and (ruta.suffix in (".nc", ".part") or ruta.name == NOMBRE_INDICE):
                ruta.unlink()
                borrados += 1
        for vacia in (carpeta, carpeta.parent):
            try:
                vacia.rmdir()
            except OSError:
                pass
    return borrados
