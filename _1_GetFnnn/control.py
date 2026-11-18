"""Lectura del control compartido de ciclos NetCDF."""
from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


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

    for fila in hoja.findall(".//m:sheetData/m:row", _NS)[1:]:
        valores = {}
        for celda in fila.findall("m:c", _NS):
            columna = "".join(ch for ch in celda.get("r", "") if ch.isalpha())
            tipo = celda.get("t")
            if tipo == "inlineStr":
                nodo = celda.find("m:is", _NS)
                valores[columna] = "".join(t.text or "" for t in nodo.findall(".//m:t", _NS)) if nodo is not None else ""
            else:
                nodo = celda.find("m:v", _NS)
                valor = nodo.text if nodo is not None else ""
                if tipo == "s" and valor:
                    valor = compartidos[int(valor)]
                valores[columna] = valor
        estado = valores.get("C", "").strip().casefold()
        if valores.get("A") == fecha and str(valores.get("B", "")).zfill(2) == ciclo:
            return estado in {"sí", "si", "true", "yes", "1"}
    return False
