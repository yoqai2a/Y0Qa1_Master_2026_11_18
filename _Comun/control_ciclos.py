"""Lectura y escritura de ``control.xlsx`` (registro matricial de ciclos creados).

Formato vigente: fecha | 00 | 06 | 12 | 18, con "Sí" en los ciclos creados.
También se lee el formato antiguo (fecha | ciclo | existe).

Este es el único módulo que conoce el formato; la descarga, la creación de NetCDF
y el visor lo usan en vez de tener cada uno su propio lector.

Uso desde línea de comandos (lo usa el workflow para reintentar publicaciones):
    python -m _Comun.control_ciclos marcar --ruta ___Data/control.xlsx --fecha 20261119 --ciclo 12
"""
from __future__ import annotations

import argparse
import io
import logging
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Iterable

from openpyxl import Workbook, load_workbook

log = logging.getLogger(__name__)

CICLOS = ("00", "06", "12", "18")
MESES_ES = ("enero", "febrero", "marzo", "abril", "mayo", "junio",
            "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")
_AFIRMATIVOS = {"sí", "si", "true", "yes", "1"}
_RE_FECHA_TEXTO = re.compile(r"(\d{1,2})\.([a-záéíóú]+)\.(\d{4})", re.IGNORECASE)


class ErrorControl(RuntimeError):
    """control.xlsx no se pudo leer o escribir."""


def es_afirmativo(valor) -> bool:
    return str(valor or "").strip().casefold() in _AFIRMATIVOS


def normalizar_fecha(valor) -> str:
    """'19.noviembre.2026' o '20261119' -> '20261119'. Cadena vacía si no es válida."""
    texto = str(valor or "").strip()
    if re.fullmatch(r"\d{8}", texto):
        return texto
    m = _RE_FECHA_TEXTO.fullmatch(texto)
    if not m or m.group(2).casefold() not in MESES_ES:
        return ""
    try:
        mes = MESES_ES.index(m.group(2).casefold()) + 1
        return datetime(int(m.group(3)), mes, int(m.group(1))).strftime("%Y%m%d")
    except ValueError:
        return ""


def etiqueta_fecha(fecha: str) -> str:
    """'20261119' -> '19.noviembre.2026'."""
    d = datetime.strptime(fecha, "%Y%m%d")
    return f"{d.day:02d}.{MESES_ES[d.month - 1]}.{d.year}"


def _filas_hoja(origen: Path | bytes) -> list[tuple]:
    try:
        fuente = io.BytesIO(origen) if isinstance(origen, (bytes, bytearray)) else origen
        libro = load_workbook(fuente, read_only=True, data_only=True)
        try:
            return list(libro.worksheets[0].iter_rows(values_only=True))
        finally:
            libro.close()
    except Exception as exc:  # openpyxl lanza varios tipos según el daño del archivo
        nombre = origen if isinstance(origen, Path) else "control.xlsx"
        raise ErrorControl(f"No se pudo leer el control de ciclos {nombre}: {exc}") from exc


def leer_filas(origen: Path | bytes) -> list[dict]:
    """Filas matriciales ``{"fecha_key", "fecha", "00", "06", "12", "18"}``, la más reciente primero.

    ``origen`` puede ser una ruta o el contenido del archivo (bytes).
    """
    filas = _filas_hoja(origen)
    if not filas:
        return []
    encabezados = [str(v or "").strip().casefold() for v in filas[0]]
    if all(c in encabezados for c in CICLOS):
        posicion = {c: encabezados.index(c) for c in CICLOS}
        salida = []
        for fila in filas[1:]:
            fecha = normalizar_fecha(fila[0] if fila else "")
            if not fecha:
                continue
            salida.append({"fecha_key": fecha, "fecha": str(fila[0]), **{
                c: str(fila[i] or "").strip() if i < len(fila) else "" for c, i in posicion.items()}})
        return sorted(salida, key=lambda f: f["fecha_key"], reverse=True)
    # Formato antiguo: fecha | ciclo | existe
    acumulado: dict[str, dict] = {}
    for fila in filas[1:]:
        if len(fila) < 3:
            continue
        fecha, ciclo = normalizar_fecha(fila[0]), str(fila[1] or "").zfill(2)
        if fecha and ciclo in CICLOS:
            registro = acumulado.setdefault(fecha, {"fecha_key": fecha, "fecha": fecha, **{c: "" for c in CICLOS}})
            registro[ciclo] = str(fila[2] or "").strip()
    return sorted(acumulado.values(), key=lambda f: f["fecha_key"], reverse=True)


def leer_ciclos(origen: Path | bytes) -> set[tuple[str, str]]:
    """Conjunto de (fecha, ciclo) marcados como creados."""
    return {(f["fecha_key"], c) for f in leer_filas(origen) for c in CICLOS if es_afirmativo(f.get(c))}


def ciclo_creado(ruta: Path, fecha: str, ciclo: str) -> bool:
    """True si el control marca como existente el ciclo solicitado."""
    if not Path(ruta).is_file():
        return False
    return (fecha, ciclo) in leer_ciclos(Path(ruta))


def escribir_control(ruta: Path, ciclos: Iterable[tuple[str, str]]) -> Path:
    """Escribe el control completo (reemplazo atómico)."""
    ruta = Path(ruta)
    por_fecha: dict[str, set[str]] = {}
    for fecha, ciclo in ciclos:
        por_fecha.setdefault(fecha, set()).add(ciclo)
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Control"
    hoja.append(["fecha", *CICLOS])
    for fecha in sorted(por_fecha, reverse=True):
        hoja.append([etiqueta_fecha(fecha), *("Sí" if c in por_fecha[fecha] else "" for c in CICLOS)])
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_name(ruta.name + ".part")
    libro.save(temporal)
    os.replace(temporal, ruta)
    return ruta


def leer_ciclos_o_respaldar(ruta: Path) -> set[tuple[str, str]]:
    """Lee los ciclos de ``ruta``. Si el archivo está dañado lo conserva como ``.corrupto``
    (para no perder el historial sin avisar) y parte de un control vacío."""
    ruta = Path(ruta)
    if not ruta.is_file():
        return set()
    try:
        return leer_ciclos(ruta)
    except ErrorControl as exc:
        copia = ruta.with_name(ruta.name + ".corrupto")
        shutil.copy2(ruta, copia)
        log.warning("%s. Se conservó una copia en %s y se crea un control nuevo.", exc, copia)
        return set()


def marcar_ciclo(ruta: Path, fecha: str, ciclo: str) -> Path:
    """Agrega un ciclo al control existente y lo guarda."""
    ciclos = leer_ciclos_o_respaldar(ruta)
    ciclos.add((fecha, ciclo))
    return escribir_control(ruta, ciclos)


def _principal(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="orden", required=True)
    marcar = sub.add_parser("marcar", help="Marca un ciclo como creado en control.xlsx")
    marcar.add_argument("--ruta", required=True, type=Path)
    marcar.add_argument("--fecha", required=True, help="AAAAMMDD")
    marcar.add_argument("--ciclo", required=True, choices=CICLOS)
    args = parser.parse_args(argv)
    if not re.fullmatch(r"\d{8}", args.fecha):
        parser.error("--fecha debe tener formato AAAAMMDD")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    marcar_ciclo(args.ruta, args.fecha, args.ciclo)
    return 0


if __name__ == "__main__":
    raise SystemExit(_principal())
