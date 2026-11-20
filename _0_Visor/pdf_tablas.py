"""Exporta las tablas de precipitación, CAPE, viento e isoterma 0 a PDF."""
from __future__ import annotations

from html import escape
from io import BytesIO

import tablas as t


VARIABLES_PDF = (
    ("tp", "Precipitación", "Precipitación total", "mm"),
    ("cape", "CAPE", "CAPE", "J/kg"),
    ("gust", "Racha de viento", "Racha de viento", "km/h"),
    ("gh_iso0", "Isoterma 0", "Isoterma 0", "m"),
)


def generar_pdf_tablas(ciclo: str, cierre: str, formato_especial: bool = False,
                       aproximar_centenas: bool = True) -> bytes:
    """Calcula las cuatro tablas del ciclo usando el cierre guardado/seleccionado."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import LongTable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, TableStyle

    puntos_dict = t.cargar_puntos()
    puntos = tuple((p["area"], p["punto"], p["lat"], p["lon"]) for p in puntos_dict)
    areas = list(dict.fromkeys(p[0] for p in puntos))
    pagina = landscape(A4)
    ancho, _ = pagina
    margen = 12 * mm
    buffer = BytesIO()
    estilos = getSampleStyleSheet()
    titulo = ParagraphStyle("TituloY0", parent=estilos["Title"], fontName="Helvetica-Bold",
                            fontSize=18, leading=21, textColor=colors.HexColor("#12304A"), spaceAfter=3 * mm)
    celda = ParagraphStyle("CeldaY0", parent=estilos["BodyText"], fontSize=7, leading=8,
                           alignment=1, spaceAfter=0, spaceBefore=0)
    cabecera = ParagraphStyle("CabeceraY0", parent=celda, fontName="Helvetica-Bold", textColor=colors.white)
    area_celda = ParagraphStyle("AreaY0", parent=celda, alignment=0)
    nota = ParagraphStyle("NotaY0", parent=estilos["BodyText"], fontSize=8, leading=10,
                          textColor=colors.HexColor("#475569"), spaceBefore=2 * mm)
    contenido = [
        Paragraph("Resumen meteorológico por área", titulo),
        Paragraph(f"Ciclo {ciclo[:8]} {ciclo[9:]}Z · Cierre UTC {cierre}Z · Viento en km/h · Precipitación en mm · CAPE en J/kg · Isoterma 0 en m.", nota),
        Spacer(1, 4 * mm),
    ]

    def pie(canvas, documento):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#CBD5E1"))
        canvas.line(margen, 9 * mm, ancho - margen, 9 * mm)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#475569"))
        canvas.drawString(margen, 5 * mm, f"Ciclo {ciclo[:8]} {ciclo[9:]}Z | Cierre {cierre}Z")
        canvas.drawRightString(ancho - margen, 5 * mm, f"Página {documento.page}")
        canvas.restoreState()

    for indice, (tipo, nombre, nombre_variable, unidad) in enumerate(VARIABLES_PDF):
        contenido.append(Paragraph(escape(nombre), estilos["Heading2"]))
        ruta = t.ruta_variable(ciclo, tipo)
        if ruta is None:
            contenido.append(Paragraph("No hay un archivo disponible para esta variable en el ciclo seleccionado.", nota))
        else:
            mtime = ruta.stat().st_mtime
            limites = t.limites_temporales(str(ruta), mtime)
            fechas = tuple(t.fechas_disponibles(str(ruta), mtime, cierre=cierre))
            if limites is None or not fechas:
                contenido.append(Paragraph("No hay horas disponibles para esta variable.", nota))
            else:
                datos = t.calcular_maximos(str(ruta), mtime, fechas, cierre, tipo, unidad,
                                           formato_especial if tipo == "gh_iso0" else False, puntos)
                etiquetas = {fecha: t._etiqueta_periodo(fecha, cierre, *limites) for fecha in fechas}
                filas = [[Paragraph("Área", cabecera)] + [
                    Paragraph(escape(etiquetas[fecha].replace(" / ", "<br/>/ ")), cabecera) for fecha in fechas
                ]]
                valores_areas = []
                for area in areas:
                    fila = [Paragraph(escape(area), area_celda)]
                    valores_fila = []
                    for fecha in fechas:
                        valores = [v for v in datos["valores"].get(fecha, {}).get(area, {}).values() if v is not None]
                        if tipo == "gh_iso0":
                            if valores and formato_especial:
                                valor = (max(v[0] for v in valores), max(v[1] for v in valores))
                            else:
                                valor = (min(v[0] for v in valores), max(v[1] for v in valores)) if valores else None
                            texto = (f"{t._formatea_isoterma(valor[0], aproximar_centenas)} / "
                                     f"{t._formatea_isoterma(valor[1], aproximar_centenas)}"
                                     if valor is not None else "-")
                        else:
                            valor = (max(valores) if tipo in {"tp", "cape", "gust"} else min(valores)) if valores else None
                            texto = f"{int(round(valor)):,}".replace(",", " ") if valor is not None else "-"
                        fila.append(Paragraph(texto, celda))
                        valores_fila.append(valor)
                    filas.append(fila)
                    valores_areas.append((area, valores_fila))

                ancho_util = ancho - 2 * margen
                ancho_area = min(120, ancho_util * 0.2)
                anchos = [ancho_area] + [(ancho_util - ancho_area) / len(fechas)] * len(fechas)
                tabla = LongTable(filas, colWidths=anchos, repeatRows=1, hAlign="LEFT")
                reglas = [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#214E73")),
                    ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD5E1")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                    ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
                if tipo in {"tp", "cape", "gust"}:
                    config = t.cargar_rangos(tipo)
                    if tipo == "gust":
                        config = t.rangos_viento_en_unidad(config, "km/h")
                    for numero_fila, (area, valores) in enumerate(valores_areas, start=1):
                        for numero_col, valor in enumerate(valores, start=1):
                            if valor is None:
                                continue
                            if tipo == "tp" and area in config.get("areas_sin_colores", []):
                                rango = config.get("color_sin_paleta", {"fondo": "#F2F2F2", "texto": "#000000"})
                                fondo, texto = rango["fondo"], rango["texto"]
                            else:
                                rangos = config.get("rangos_por_area", {}).get(area, config["rangos"])
                                fondo, texto = t._color_de(valor, rangos)
                            if fondo:
                                reglas.extend([
                                    ("BACKGROUND", (numero_col, numero_fila), (numero_col, numero_fila), colors.HexColor(fondo)),
                                    ("TEXTCOLOR", (numero_col, numero_fila), (numero_col, numero_fila), colors.HexColor(texto)),
                                ])
                tabla.setStyle(TableStyle(reglas))
                contenido.append(tabla)
                if any(etiqueta.endswith("*") for etiqueta in etiquetas.values()):
                    contenido.append(Paragraph("* Intervalo con datos parciales.", nota))
                contenido.append(Paragraph(f"{nombre_variable} · {unidad} · {ruta.name}", nota))
        if indice < len(VARIABLES_PDF) - 1:
            contenido.append(PageBreak())

    documento = SimpleDocTemplate(buffer, pagesize=pagina, leftMargin=margen, rightMargin=margen,
                                  topMargin=12 * mm, bottomMargin=14 * mm,
                                  title=f"Resumen meteorológico {ciclo} {cierre}Z", author="Y0Qa1 Visor")
    documento.build(contenido, onFirstPage=pie, onLaterPages=pie)
    return buffer.getvalue()
