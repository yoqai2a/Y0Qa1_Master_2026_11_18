"""Exporta las tablas meteorológicas por área en PDF (A4 horizontal) con fpdf2.

Usa los mismos módulos de cálculo y de colores que la pantalla de Tablas, de modo que el PDF
y la tabla en pantalla nunca difieran.
"""
from __future__ import annotations

from fpdf import FPDF

from . import calculo as ct
from . import datos as dc
from . import estilos as et

# (clave, título de la página, nombre de la variable, unidad)
VARIABLES_PDF = (
    ("tp", "Precipitación", "Precipitación total", "mm"),
    ("cape", "CAPE", "CAPE", "J/kg"),
    ("gust", "Racha de viento", "Racha de viento", "km/h"),
    ("gh_iso0", "Isoterma 0", "Isoterma 0", "m"),
)
TIPOS_CON_PALETA = {"tp", "cape", "gust"}

# A4 horizontal en puntos; las coordenadas Y se miden desde el borde superior.
PAGE_W, PAGE_H = 842.0, 595.0
LEFT, RIGHT, BOTTOM = 34.0, 34.0, 42.0
Y_TABLA = 96.0
ALTO_CABECERA, ALTO_FILA = 34.0, 22.0
AZUL_TITULO, GRIS_TEXTO, TINTA = "#12304A", "#475569", "#202938"


def _rgb(hexadecimal: str) -> tuple[int, int, int]:
    valor = hexadecimal.lstrip("#")
    if len(valor) == 3:
        valor = "".join(c * 2 for c in valor)
    return tuple(int(valor[i:i + 2], 16) for i in (0, 2, 4))


def _l1(texto) -> str:
    """Las fuentes base del PDF son Latin-1: lo que no cabe se reemplaza por '?'."""
    return str(texto).encode("latin-1", errors="replace").decode("latin-1")


class _Documento(FPDF):
    def __init__(self, ciclo: str, cierre: str) -> None:
        super().__init__(orientation="L", unit="pt", format="A4")
        self.set_auto_page_break(False)
        self.set_margins(LEFT, 0, RIGHT)
        self.set_title(f"Resumen meteorologico por area {ciclo} {cierre}Z")
        self.set_author("Y0Qa1")
        self.ciclo, self.cierre = ciclo, cierre
        self.numero = 0

    def texto(self, x: float, y: float, contenido, tamano: float = 8, color: str = TINTA,
              negrita: bool = False, alinear: str = "left") -> None:
        contenido = _l1(contenido)
        self.set_font("Helvetica", "B" if negrita else "", tamano)
        self.set_text_color(*_rgb(color))
        ancho = self.get_string_width(contenido)
        if alinear == "center":
            x -= ancho / 2
        elif alinear == "right":
            x -= ancho
        self.text(x, y, contenido)

    def caja(self, x: float, y: float, ancho: float, alto: float, fondo: str, borde: str = "#CBD5E1") -> None:
        self.set_fill_color(*_rgb(fondo))
        self.set_draw_color(*_rgb(borde))
        self.set_line_width(0.45)
        self.rect(x, y, ancho, alto, style="DF")

    def pagina(self, nombre_tabla: str, continuacion: bool = False) -> None:
        self.add_page()
        self.numero += 1
        ciclo = f"{self.ciclo[:8]} {self.ciclo[9:]}Z"
        self.texto(LEFT, 38, "Resumen meteorológico por área", 17, AZUL_TITULO, True)
        self.texto(LEFT, 56, f"Ciclo {ciclo} | Cierre UTC {self.cierre}Z | Viento km/h | Precipitación mm "
                             "| CAPE J/kg | Isoterma 0 m", 8, GRIS_TEXTO)
        self.texto(LEFT, 82, nombre_tabla + (" - continuación" if continuacion else ""), 12, AZUL_TITULO, True)
        self.set_draw_color(*_rgb("#CCD6E0"))
        self.set_line_width(0.5)
        self.line(LEFT, PAGE_H - 29, PAGE_W - RIGHT, PAGE_H - 29)
        self.texto(LEFT, PAGE_H - 16, f"Ciclo {ciclo} | Cierre {self.cierre}Z", 8, GRIS_TEXTO)
        self.texto(PAGE_W - RIGHT, PAGE_H - 16, f"Página {self.numero}", 8, GRIS_TEXTO, alinear="right")


def _cabecera(pdf: _Documento, y: float, posiciones: list[float], etiquetas: list[str]) -> None:
    for col in range(len(posiciones) - 1):
        x, ancho = posiciones[col], posiciones[col + 1] - posiciones[col]
        pdf.caja(x, y, ancho, ALTO_CABECERA, "#214E73", "#FFFFFF")
        if col == 0:
            pdf.texto(x + 5, y + 21, "Área", 8, "#FFFFFF", True)
        else:
            partes = etiquetas[col - 1].split(" / ")
            pdf.texto(x + ancho / 2, y + 14, partes[0], 6.5, "#FFFFFF", True, "center")
            pdf.texto(x + ancho / 2, y + 27, ("/ " + partes[1]) if len(partes) > 1 else "", 6.5,
                      "#FFFFFF", True, "center")


def _texto_celda(valor, tipo: str, centenas: bool) -> str:
    if valor is None:
        return "-"
    if tipo == "gh_iso0":
        return f"{ct.formatea_isoterma(valor[0], centenas)} / {ct.formatea_isoterma(valor[1], centenas)}"
    return f"{int(round(valor)):,}".replace(",", " ")


def _colores_celda(valor, tipo: str, area: str, configuracion: dict | None) -> tuple[str, str]:
    fondo, tinta = "#FFFFFF", TINTA
    if valor is None or not configuracion:
        return fondo, tinta
    if tipo == "tp" and area in configuracion.get("areas_sin_colores", []):
        paleta = configuracion.get("color_sin_paleta", {"fondo": "#F2F2F2", "texto": "#000000"})
        return paleta["fondo"], paleta["texto"]
    rangos = configuracion.get("rangos_por_area", {}).get(area, configuracion["rangos"])
    relleno, color_texto = et.color_de(valor, rangos)
    return (relleno, color_texto) if relleno else (fondo, tinta)


def generar_pdf_tablas(ciclo: str, cierre: str, formato_especial: bool = False,
                       aproximar_centenas: bool = True) -> bytes:
    """Calcula y entrega las cuatro tablas en páginas A4 horizontales."""
    puntos = dc.cargar_puntos()
    areas = list(dict.fromkeys(p.area for p in puntos))
    pdf = _Documento(ciclo, cierre)

    for tipo, nombre, nombre_variable, unidad in VARIABLES_PDF:
        pdf.pagina(nombre)
        ruta = dc.ruta_variable(ciclo, tipo)
        if ruta is None:
            pdf.texto(LEFT, 112, "No hay un archivo disponible para esta variable en el ciclo seleccionado.", 9)
            continue
        mtime = ruta.stat().st_mtime
        limites = ct.limites_temporales(str(ruta), mtime)
        fechas = tuple(ct.fechas_disponibles(str(ruta), mtime, cierre=cierre))
        if limites is None or not fechas:
            pdf.texto(LEFT, 112, "No hay horas disponibles para esta variable.", 9)
            continue

        especial = formato_especial if tipo == "gh_iso0" else False
        datos = ct.calcular_maximos(str(ruta), mtime, fechas, cierre, tipo, unidad, especial, puntos)
        etiquetas = [ct.etiqueta_periodo(fecha, cierre, *limites) for fecha in fechas]
        configuracion = et.config_colores(tipo, unidad) if tipo in TIPOS_CON_PALETA else None

        ancho_util = PAGE_W - LEFT - RIGHT
        ancho_area = min(120.0, ancho_util * 0.2)
        ancho_fecha = (ancho_util - ancho_area) / len(fechas)
        posiciones = [LEFT, LEFT + ancho_area]
        for _ in fechas:
            posiciones.append(posiciones[-1] + ancho_fecha)

        y = Y_TABLA
        _cabecera(pdf, y, posiciones, etiquetas)
        y += ALTO_CABECERA
        for area in areas:
            if y + ALTO_FILA > PAGE_H - (BOTTOM + 8):
                pdf.pagina(nombre, continuacion=True)
                y = Y_TABLA
                _cabecera(pdf, y, posiciones, etiquetas)
                y += ALTO_CABECERA
            valores = [ct.resumen_area(datos, fecha, area, tipo, especial) for fecha in fechas]
            for col in range(len(fechas) + 1):
                x, ancho = posiciones[col], posiciones[col + 1] - posiciones[col]
                if col == 0:
                    pdf.caja(x, y, ancho, ALTO_FILA, "#FFFFFF")
                    pdf.texto(x + 5, y + 14, area, 7.2, TINTA)
                else:
                    valor = valores[col - 1]
                    fondo, tinta = _colores_celda(valor, tipo, area, configuracion)
                    pdf.caja(x, y, ancho, ALTO_FILA, fondo)
                    pdf.texto(x + ancho / 2, y + 14, _texto_celda(valor, tipo, aproximar_centenas),
                              7.2, tinta, True, "center")
            y += ALTO_FILA

        if any(etiqueta.endswith("*") for etiqueta in etiquetas):
            if y > PAGE_H - (BOTTOM + 18):
                pdf.pagina(nombre, continuacion=True)
                y = 100.0
            pdf.texto(LEFT, y + 12, "* Intervalo con datos parciales.", 8, GRIS_TEXTO)
            y += 13
        if y <= PAGE_H - (BOTTOM + 10):
            pdf.texto(LEFT, y + 12, f"{nombre_variable} | Unidad: {unidad} | Archivo: {ruta.name}", 8, GRIS_TEXTO)

    return bytes(pdf.output())
