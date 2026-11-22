"""Índice para el visor, puntero al último ciclo y limpieza de ciclos antiguos."""
from __future__ import annotations

import json
import os
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

from .conversion import ResultadoConversion

NOMBRE_INDICE = "Indice.json"
NOMBRE_ULTIMO = "ultimo.json"
NOMBRE_CONTROL = "control.xlsx"
_RE_FECHA = re.compile(r"\d{8}")
_MESES_ES = ("enero", "febrero", "marzo", "abril", "mayo", "junio",
             "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")
_CICLOS = ("00", "06", "12", "18")


def _fecha_control(fecha: str) -> str:
    d = datetime.strptime(fecha, "%Y%m%d")
    return f"{d.day:02d}.{_MESES_ES[d.month - 1]}.{d.year}"


def _fecha_normalizada(valor: str) -> str | None:
    valor = valor.strip()
    if _RE_FECHA.fullmatch(valor):
        return valor
    m = re.fullmatch(r"(\d{1,2})\.([a-záéíóú]+)\.(\d{4})", valor, re.I)
    if not m:
        return None
    try:
        mes = _MESES_ES.index(m.group(2).casefold()) + 1
        return f"{int(m.group(3)):04d}{mes:02d}{int(m.group(1)):02d}"
    except (ValueError, IndexError):
        return None


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
    """Registro matricial: fecha | 00 | 06 | 12 | 18."""
    ruta = raiz_datos / NOMBRE_CONTROL
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    ciclos: set[tuple[str, str]] = set()
    if ruta.is_file():
        try:
            with zipfile.ZipFile(ruta) as libro:
                hoja = ET.fromstring(libro.read("xl/worksheets/sheet1.xml"))
                compartidos = []
                if "xl/sharedStrings.xml" in libro.namelist():
                    raiz_compartidos = ET.fromstring(libro.read("xl/sharedStrings.xml"))
                    compartidos = ["".join(t.text or "" for t in si.findall(".//m:t", ns))
                                   for si in raiz_compartidos.findall("m:si", ns)]
            filas_xml = hoja.findall(".//m:sheetData/m:row", ns)
            def celdas(fila):
                salida = {}
                for celda in fila.findall("m:c", ns):
                    ref = celda.get("r", "")
                    columna = "".join(ch for ch in ref if ch.isalpha())
                    texto = celda.find("m:is/m:t", ns)
                    numero = celda.find("m:v", ns)
                    valor = (texto.text or "") if texto is not None else (numero.text or "") if numero is not None else ""
                    if celda.get("t") == "s" and valor:
                        valor = compartidos[int(valor)]
                    salida[columna] = valor
                return salida
            if filas_xml:
                encabezados = celdas(filas_xml[0])
                por_columna = {str(v).strip().zfill(2): k for k, v in encabezados.items() if str(v).strip() in _CICLOS}
                if por_columna:
                    for fila in filas_xml[1:]:
                        valores = celdas(fila)
                        fecha = _fecha_normalizada(valores.get("A", ""))
                        if fecha:
                            for ciclo, columna in por_columna.items():
                                if (valores.get(columna) or "").strip().casefold() in {"sí", "si", "true", "yes", "1"}:
                                    ciclos.add((fecha, ciclo))
                else:  # Compatibilidad con el formato antiguo: fecha | ciclo | existe
                    for fila in filas_xml[1:]:
                        valores = celdas(fila)
                        fecha = _fecha_normalizada(valores.get("A", ""))
                        ciclo = str(valores.get("B", "")).zfill(2)
                        if fecha and ciclo in _CICLOS and str(valores.get("C", "")).strip().casefold() in {"sí", "si", "true", "yes", "1"}:
                            ciclos.add((fecha, ciclo))
        except (OSError, KeyError, zipfile.BadZipFile, ET.ParseError):
            ciclos = {}
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

    def col(n: int) -> str:
        return chr(64 + n)

    por_fecha: dict[str, set[str]] = {}
    for fecha, ciclo in ciclos:
        por_fecha.setdefault(fecha, set()).add(ciclo)
    filas = [("fecha", *_CICLOS)]
    for fecha in sorted(por_fecha, reverse=True):
        filas.append((_fecha_control(fecha), *("Sí" if ciclo in por_fecha[fecha] else "" for ciclo in _CICLOS)))
    sheet = ET.Element("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}worksheet")
    data = ET.SubElement(sheet, "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheetData")
    for i, valores in enumerate(filas, 1):
        fila = ET.SubElement(data, "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row", {"r": str(i)})
        for j, valor in enumerate(valores, 1):
            celda = ET.SubElement(fila, "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}c",
                                  {"r": f"{col(j)}{i}", "t": "inlineStr"})
            inline = ET.SubElement(celda, "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}is")
            ET.SubElement(inline, "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t").text = valor
    temporal = ruta.with_name(ruta.name + ".part")
    with zipfile.ZipFile(temporal, "w", zipfile.ZIP_DEFLATED) as libro:
        libro.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        libro.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        libro.writestr("xl/workbook.xml", '<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Control" sheetId="1" r:id="rId1"/></sheets></workbook>')
        libro.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        libro.writestr("xl/worksheets/sheet1.xml", ET.tostring(sheet, encoding="utf-8", xml_declaration=True))
    os.replace(temporal, ruta)
    return ruta


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
