"""Lectura del control compartido de ciclos NetCDF."""
from __future__ import annotations

import zipfile
import re
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_MESES = {n: i for i, n in enumerate(("enero", "febrero", "marzo", "abril", "mayo", "junio",
                                      "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"), 1)}


def _texto_celda(celda, compartidos):
    tipo = celda.get("t")
    if tipo == "inlineStr":
        nodo = celda.find("m:is", _NS)
        return "".join(t.text or "" for t in nodo.findall(".//m:t", _NS)) if nodo is not None else ""
    nodo = celda.find("m:v", _NS)
    valor = nodo.text if nodo is not None else ""
    if tipo == "s" and valor:
        valor = compartidos[int(valor)]
    return valor


def _fecha(valor):
    valor = str(valor or "").strip()
    if re.fullmatch(r"\d{8}", valor):
        return valor
    m = re.fullmatch(r"(\d{1,2})\.([a-záéíóú]+)\.(\d{4})", valor, re.I)
    if not m or m.group(2).casefold() not in _MESES:
        return ""
    try:
        return datetime(int(m.group(3)), _MESES[m.group(2).casefold()], int(m.group(1))).strftime("%Y%m%d")
    except ValueError:
        return ""


def ciclo_creado(ruta: Path, fecha: str, ciclo: str) -> bool:
    """True si control.xlsx marca como existente el ciclo solicitado."""
    if not ruta.is_file():
        return False
    try:
        with zipfile.ZipFile(ruta) as libro:
            hoja = ET.fromstring(libro.read("xl/worksheets/sheet1.xml"))
            compartidos = []
            if "xl/sharedStrings.xml" in libro.namelist():
                raices = ET.fromstring(libro.read("xl/sharedStrings.xml"))
                compartidos = ["".join(t.text or "" for t in si.findall(".//m:t", _NS))
                               for si in raices.findall("m:si", _NS)]
    except (OSError, KeyError, zipfile.BadZipFile, ET.ParseError) as exc:
        raise RuntimeError(f"No se pudo leer el control de ciclos {ruta}: {exc}") from exc

    filas = hoja.findall(".//m:sheetData/m:row", _NS)
    encabezados = {}
    if filas:
        for celda in filas[0].findall("m:c", _NS):
            columna = "".join(ch for ch in celda.get("r", "") if ch.isalpha())
            encabezados[columna] = _texto_celda(celda, compartidos).strip()
    columnas_ciclo = {v.zfill(2): k for k, v in encabezados.items() if v in {"00", "06", "12", "18"}}
    for fila in filas[1:]:
        valores = {}
        for celda in fila.findall("m:c", _NS):
            columna = "".join(ch for ch in celda.get("r", "") if ch.isalpha())
            valores[columna] = _texto_celda(celda, compartidos)
        if _fecha(valores.get("A")) == fecha and columnas_ciclo:
            estado = valores.get(columnas_ciclo.get(ciclo, ""), "").strip().casefold()
            return estado in {"sí", "si", "true", "yes", "1"}
        if _fecha(valores.get("A")) == fecha and str(valores.get("B", "")).zfill(2) == ciclo:
            estado = valores.get("C", "").strip().casefold()
            return estado in {"sí", "si", "true", "yes", "1"}
    return False
