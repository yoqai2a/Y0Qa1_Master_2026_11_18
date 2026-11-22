"""Exporta tablas meteorológicas en PDF usando solo la biblioteca estándar."""
from __future__ import annotations

import tablas as t


VARIABLES_PDF = (
    ("tp", "Precipitación", "Precipitación total", "mm"),
    ("cape", "CAPE", "CAPE", "J/kg"),
    ("gust", "Racha de viento", "Racha de viento", "km/h"),
    ("gh_iso0", "Isoterma 0", "Isoterma 0", "m"),
)

# A4 horizontal en puntos PDF.
PAGE_W, PAGE_H = 842.0, 595.0
LEFT, RIGHT, BOTTOM = 34.0, 34.0, 42.0


def _color(hexadecimal: str) -> tuple[float, float, float]:
    valor = hexadecimal.lstrip("#")
    return tuple(int(valor[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _pdf_texto(valor: str) -> str:
    """Codifica texto cp1252 como literal PDF, escapando los bytes especiales."""
    datos = str(valor).encode("cp1252", errors="replace")
    salida = []
    for byte in datos:
        if byte in (40, 41, 92):
            salida.append("\\" + chr(byte))
        elif 32 <= byte <= 126:
            salida.append(chr(byte))
        else:
            salida.append(f"\\{byte:03o}")
    return "".join(salida)


def _texto(comandos: list[str], x: float, y: float, texto: str, tamano: float = 8,
           color: str = "#202938", negrita: bool = False, alinear: str = "left") -> None:
    texto = str(texto)
    # Aproximación de ancho Helvetica suficiente para centrar texto en las celdas.
    ancho = len(texto) * tamano * (0.54 if negrita else 0.50)
    if alinear == "center":
        x -= ancho / 2
    elif alinear == "right":
        x -= ancho
    r, g, b = _color(color)
    fuente = "F2" if negrita else "F1"
    comandos.append(f"BT /{fuente} {tamano:.2f} Tf {r:.4f} {g:.4f} {b:.4f} rg {x:.2f} {y:.2f} Td ({_pdf_texto(texto)}) Tj ET")


def _rect(comandos: list[str], x: float, y: float, ancho: float, alto: float,
          fondo: str, borde: str = "#CBD5E1") -> None:
    r, g, b = _color(fondo)
    br, bg, bb = _color(borde)
    comandos.append(f"q {r:.4f} {g:.4f} {b:.4f} rg {br:.4f} {bg:.4f} {bb:.4f} RG 0.45 w {x:.2f} {y:.2f} {ancho:.2f} {alto:.2f} re B Q")


def _pie(comandos: list[str], ciclo: str, cierre: str, pagina: int) -> None:
    comandos.append(f"0.80 0.84 0.88 RG 0.5 w {LEFT:.2f} 29 m {PAGE_W - RIGHT:.2f} 29 l S")
    _texto(comandos, LEFT, 16, f"Ciclo {ciclo[:8]} {ciclo[9:]}Z | Cierre {cierre}Z", 8, "#475569")
    _texto(comandos, PAGE_W - RIGHT, 16, f"Página {pagina}", 8, "#475569", alinear="right")


def _nueva_pagina(ciclo: str, cierre: str, nombre_tabla: str, pagina: int,
                  continuacion: bool = False) -> list[str]:
    comandos = ["1 J 1 j"]
    _texto(comandos, LEFT, PAGE_H - 38, "Resumen meteorológico por área", 17, "#12304A", True)
    _texto(comandos, LEFT, PAGE_H - 56,
           f"Ciclo {ciclo[:8]} {ciclo[9:]}Z | Cierre UTC {cierre}Z | Viento km/h | Precipitación mm | CAPE J/kg | Isoterma 0 m",
           8, "#475569")
    sufijo = " - continuación" if continuacion else ""
    _texto(comandos, LEFT, PAGE_H - 82, nombre_tabla + sufijo, 12, "#12304A", True)
    _pie(comandos, ciclo, cierre, pagina)
    return comandos


def _hacer_pdf(paginas: list[list[str]]) -> bytes:
    objetos: list[bytes] = [b""]
    objetos.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    paginas_ids = [5 + 2 * indice for indice in range(len(paginas))]
    referencias = " ".join(f"{numero} 0 R" for numero in paginas_ids)
    objetos.append(f"<< /Type /Pages /Kids [{referencias}] /Count {len(paginas)} >>".encode("ascii"))
    objetos.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    objetos.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    for indice, comandos in enumerate(paginas):
        id_pagina = 5 + 2 * indice
        id_stream = id_pagina + 1
        stream = ("\n".join(comandos) + "\n").encode("ascii")
        objetos.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_W:.0f} {PAGE_H:.0f}] "
            f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {id_stream} 0 R >>".encode("ascii")
        )
        objetos.append(f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"endstream")

    salida = bytearray(b"%PDF-1.4\n%Y0Qa1\n")
    offsets = [0]
    for numero, contenido in enumerate(objetos[1:], start=1):
        offsets.append(len(salida))
        salida.extend(f"{numero} 0 obj\n".encode("ascii"))
        salida.extend(contenido)
        salida.extend(b"\nendobj\n")
    inicio_xref = len(salida)
    salida.extend(f"xref\n0 {len(objetos)}\n0000000000 65535 f \n".encode("ascii"))
    for offset in offsets[1:]:
        salida.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    salida.extend(f"trailer\n<< /Size {len(objetos)} /Root 1 0 R >>\nstartxref\n{inicio_xref}\n%%EOF\n".encode("ascii"))
    return bytes(salida)


def generar_pdf_tablas(ciclo: str, cierre: str, formato_especial: bool = False,
                       aproximar_centenas: bool = True) -> bytes:
    """Calcula y entrega las cuatro tablas en páginas A4 horizontales."""
    puntos_dict = t.cargar_puntos()
    puntos = tuple((p["area"], p["punto"], p["lat"], p["lon"]) for p in puntos_dict)
    areas = list(dict.fromkeys(p[0] for p in puntos))
    paginas: list[list[str]] = []
    siguiente_numero = 1

    for tipo, nombre, nombre_variable, unidad in VARIABLES_PDF:
        comandos = _nueva_pagina(ciclo, cierre, nombre, siguiente_numero)
        siguiente_numero += 1
        ruta = t.ruta_variable(ciclo, tipo)
        if ruta is None:
            _texto(comandos, LEFT, PAGE_H - 112,
                   "No hay un archivo disponible para esta variable en el ciclo seleccionado.", 9)
            paginas.append(comandos)
            continue

        mtime = ruta.stat().st_mtime
        limites = t.limites_temporales(str(ruta), mtime)
        fechas = tuple(t.fechas_disponibles(str(ruta), mtime, cierre=cierre))
        if limites is None or not fechas:
            _texto(comandos, LEFT, PAGE_H - 112, "No hay horas disponibles para esta variable.", 9)
            paginas.append(comandos)
            continue

        datos = t.calcular_maximos(str(ruta), mtime, fechas, cierre, tipo, unidad,
                                   formato_especial if tipo == "gh_iso0" else False, puntos)
        etiquetas = {fecha: t._etiqueta_periodo(fecha, cierre, *limites) for fecha in fechas}
        ancho_util = PAGE_W - LEFT - RIGHT
        ancho_area = min(120.0, ancho_util * 0.2)
        ancho_fecha = (ancho_util - ancho_area) / len(fechas)
        altura_cabecera, altura_fila = 34.0, 22.0
        y_superior = PAGE_H - 96

        # Encabezados con los períodos en dos líneas para aprovechar el ancho.
        posiciones = [LEFT]
        for indice in range(len(fechas) + 1):
            posiciones.append(posiciones[-1] + (ancho_area if indice == 0 else ancho_fecha))
        for col, x in enumerate(posiciones[:-1]):
            ancho_col = posiciones[col + 1] - x
            _rect(comandos, x, y_superior - altura_cabecera, ancho_col, altura_cabecera, "#214E73", "#FFFFFF")
            if col == 0:
                _texto(comandos, x + 5, y_superior - 21, "Área", 8, "#FFFFFF", True)
            else:
                partes = etiquetas[fechas[col - 1]].split(" / ")
                _texto(comandos, x + ancho_col / 2, y_superior - 14, partes[0], 6.5, "#FFFFFF", True, "center")
                _texto(comandos, x + ancho_col / 2, y_superior - 27,
                       ("/ " + partes[1]) if len(partes) > 1 else "", 6.5, "#FFFFFF", True, "center")
        y_superior -= altura_cabecera

        configuracion = t.cargar_rangos(tipo) if tipo in {"tp", "cape", "gust"} else None
        if tipo == "gust" and configuracion:
            configuracion = t.rangos_viento_en_unidad(configuracion, "km/h")

        for area in areas:
            if y_superior - altura_fila < BOTTOM + 8:
                paginas.append(comandos)
                comandos = _nueva_pagina(ciclo, cierre, nombre, siguiente_numero, continuacion=True)
                siguiente_numero += 1
                y_superior = PAGE_H - 96
                for col, x in enumerate(posiciones[:-1]):
                    ancho_col = posiciones[col + 1] - x
                    _rect(comandos, x, y_superior - altura_cabecera, ancho_col, altura_cabecera, "#214E73", "#FFFFFF")
                    if col == 0:
                        _texto(comandos, x + 5, y_superior - 21, "Área", 8, "#FFFFFF", True)
                    else:
                        partes = etiquetas[fechas[col - 1]].split(" / ")
                        _texto(comandos, x + ancho_col / 2, y_superior - 14, partes[0], 6.5, "#FFFFFF", True, "center")
                        _texto(comandos, x + ancho_col / 2, y_superior - 27,
                               ("/ " + partes[1]) if len(partes) > 1 else "", 6.5, "#FFFFFF", True, "center")
                y_superior -= altura_cabecera

            valores_celdas = []
            for fecha in fechas:
                valores = [valor for valor in datos["valores"].get(fecha, {}).get(area, {}).values()
                           if valor is not None]
                if tipo == "gh_iso0":
                    if valores and formato_especial:
                        valor = max(v[0] for v in valores), max(v[1] for v in valores)
                    else:
                        valor = (min(v[0] for v in valores), max(v[1] for v in valores)) if valores else None
                    texto = (f"{t._formatea_isoterma(valor[0], aproximar_centenas)} / "
                             f"{t._formatea_isoterma(valor[1], aproximar_centenas)}") if valor is not None else "-"
                else:
                    valor = (max(valores) if tipo in {"tp", "cape", "gust"} else min(valores)) if valores else None
                    texto = f"{int(round(valor)):,}".replace(",", " ") if valor is not None else "-"
                valores_celdas.append((valor, texto))

            x = LEFT
            for col in range(len(fechas) + 1):
                ancho_col = ancho_area if col == 0 else ancho_fecha
                fondo, color_texto = "#FFFFFF", "#202938"
                valor = None if col == 0 else valores_celdas[col - 1][0]
                if col > 0 and valor is not None and configuracion:
                    if tipo == "tp" and area in configuracion.get("areas_sin_colores", []):
                        paleta = configuracion.get("color_sin_paleta", {"fondo": "#F2F2F2", "texto": "#000000"})
                        fondo, color_texto = paleta["fondo"], paleta["texto"]
                    else:
                        rangos = configuracion.get("rangos_por_area", {}).get(area, configuracion["rangos"])
                        relleno, tinta = t._color_de(valor, rangos)
                        if relleno:
                            fondo, color_texto = relleno, tinta
                _rect(comandos, x, y_superior - altura_fila, ancho_col, altura_fila, fondo)
                if col == 0:
                    contenido = area
                    _texto(comandos, x + 5, y_superior - 14, contenido, 7.2, color_texto)
                else:
                    contenido = valores_celdas[col - 1][1]
                    _texto(comandos, x + ancho_col / 2, y_superior - 14, contenido, 7.2, color_texto, True, "center")
                x += ancho_col
            y_superior -= altura_fila

        if any(etiqueta.endswith("*") for etiqueta in etiquetas.values()):
            if y_superior < BOTTOM + 18:
                paginas.append(comandos)
                comandos = _nueva_pagina(ciclo, cierre, nombre, siguiente_numero, continuacion=True)
                siguiente_numero += 1
                y_superior = PAGE_H - 100
            _texto(comandos, LEFT, y_superior - 4, "* Intervalo con datos parciales.", 8, "#475569")
            y_superior -= 13
        if y_superior >= BOTTOM + 10:
            _texto(comandos, LEFT, y_superior - 4, f"{nombre_variable} | Unidad: {unidad} | Archivo: {ruta.name}", 8, "#475569")
        paginas.append(comandos)

    return _hacer_pdf(paginas)
