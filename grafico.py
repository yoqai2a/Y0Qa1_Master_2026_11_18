"""Figura tiempo x presión (matplotlib, sin pyplot: segura para varios usuarios a la vez)."""
from __future__ import annotations

import io
import math

import matplotlib.dates as mdates
import numpy as np
from matplotlib import colormaps
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.figure import Figure
from matplotlib.ticker import NullLocator

from .calculo import Seccion
from .config import Vista


def niveles_de_color(vista: Vista, unidad: str) -> np.ndarray:
    u = vista.unidades[unidad]
    return np.arange(u.minimo, u.maximo + u.paso * 0.5, u.paso)


def _paleta_y_norma(vista: Vista, niveles: np.ndarray):
    """(paleta, norma). Con ``centro`` el valor central cae en el medio de la paleta (colores fríos
    abajo y cálidos arriba), con una escala común a ambos lados."""
    base = colormaps[vista.paleta]
    if vista.centro is None:
        return base, None
    paso = niveles[1] - niveles[0]
    medios = list((niveles[:-1] + niveles[1:]) / 2)
    if vista.extension in ("min", "both"):
        medios.insert(0, niveles[0] - paso / 2)
    if vista.extension in ("max", "both"):
        medios.append(niveles[-1] + paso / 2)
    # Cada lado usa su propio rango: el color más intenso queda en el extremo de cada lado.
    bajo = (vista.centro - niveles[0]) or 1.0
    alto = (niveles[-1] - vista.centro) or 1.0

    def posicion(m: float) -> float:
        return 0.5 + 0.5 * (m - vista.centro) / alto if m >= vista.centro else 0.5 - 0.5 * (vista.centro - m) / bajo

    colores = [base(float(np.clip(posicion(m), 0, 1))) for m in medios]
    paleta = ListedColormap(colores)
    return paleta, BoundaryNorm(niveles, ncolors=len(colores), extend=vista.extension)


def _formato(valor: float) -> str:
    return f"{valor:g}"


def _intervalo_barbas_horas(dias: float) -> int:
    return 3 if dias <= 2.5 else 6 if dias <= 4.5 else 12


def _dibujar_barbas(ax, seccion: Seccion, x: np.ndarray, dias: float) -> None:
    paso_h = _intervalo_barbas_horas(dias)
    columnas = [i for i, h in enumerate(seccion.horas) if h.hour % paso_h == 0 and h.minute == 0]
    filas = list(range(len(seccion.niveles)))
    if len(filas) > 12:
        filas = filas[::2]
    if not columnas or not filas:
        return
    xs, ys = np.meshgrid(x[columnas], seccion.niveles[filas])
    u = seccion.u_nudos[np.ix_(filas, columnas)]
    v = seccion.v_nudos[np.ix_(filas, columnas)]
    valido = np.isfinite(u) & np.isfinite(v)
    ax.barbs(xs[valido], ys[valido], u[valido], v[valido], length=5.2, linewidth=0.7,
             color="#1f1f1f", zorder=5)


def figura_corte(seccion: Seccion, vista: Vista, titulo: str, subtitulo: str,
                 escala_vertical: str = "lineal", con_barbas: bool = True) -> Figure:
    """Dibuja el corte: colores, contornos resaltados, barbas opcionales y ejes de tiempo y presión."""
    niveles_c = niveles_de_color(vista, seccion.unidad)
    x = mdates.date2num(seccion.horas.to_pydatetime())
    y = seccion.niveles
    z = np.ma.masked_invalid(seccion.valores)

    fig = Figure(figsize=(12.5, 5.8), dpi=100, layout="constrained")
    ax = fig.subplots()
    paleta, norma = _paleta_y_norma(vista, niveles_c)
    relleno = ax.contourf(x, y, z, levels=niveles_c, cmap=paleta, norm=norma, extend=vista.extension, zorder=1)
    # líneas finas en cada nivel de color para leer mejor los valores
    ax.contour(x, y, z, levels=niveles_c, colors="#00000033", linewidths=0.35, zorder=2)
    for contorno in vista.contornos:
        if np.nanmin(seccion.valores) <= contorno.valor <= np.nanmax(seccion.valores):
            lineas = ax.contour(x, y, z, levels=[contorno.valor], colors=[contorno.color],
                                linewidths=contorno.ancho, zorder=3)
            ax.clabel(lineas, fmt={contorno.valor: contorno.etiqueta}, fontsize=8, inline=True)
    dias = float(x[-1] - x[0])
    if con_barbas and vista.barbas and seccion.u_nudos is not None:
        _dibujar_barbas(ax, seccion, x, dias)

    # Eje vertical: presión decreciente hacia arriba
    if escala_vertical == "logaritmica":
        ax.set_yscale("log")
    ax.set_ylim(seccion.niveles.max(), seccion.niveles.min())
    ax.set_yticks(seccion.niveles)
    # En escala logarítmica los niveles bajos se juntan: se rotulan solo los múltiplos de 50 hPa.
    rotular_todos = escala_vertical != "logaritmica" or len(seccion.niveles) <= 14
    ax.set_yticklabels([f"{int(n)}" if rotular_todos or int(n) % 50 == 0 else "" for n in seccion.niveles], fontsize=8)
    ax.yaxis.set_minor_locator(NullLocator())
    ax.set_ylabel("Presión (hPa)")

    # Eje horizontal: horas UTC, con una línea en cada 00Z
    intervalo = 3 if dias <= 1.5 else 6 if dias <= 3.5 else 12 if dias <= 6.5 else 24
    ax.xaxis.set_major_locator(mdates.HourLocator(byhour=range(0, 24, intervalo)))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m\n%HZ"))
    ax.tick_params(axis="x", labelsize=8)
    ax.set_xlim(x[0], x[-1])
    primero = math.ceil(x[0])
    for medianoche in np.arange(primero, x[-1] + 1e-9, 1.0):
        ax.axvline(medianoche, color="#333333", linewidth=0.7, linestyle=":", zorder=4)
    ax.set_xlabel("Hora UTC")
    ax.grid(axis="y", color="#00000014", linewidth=0.5)

    barra = fig.colorbar(relleno, ax=ax, pad=0.012, fraction=0.04)
    barra.set_label(seccion.unidad)
    paso_marcas = max(1, len(niveles_c) // 12)
    barra.set_ticks(niveles_c[::paso_marcas])
    barra.ax.set_yticklabels([_formato(v) for v in niveles_c[::paso_marcas]], fontsize=8)
    ax.set_title(f"{titulo}\n{subtitulo}", loc="left", fontsize=11)
    if con_barbas and vista.barbas:
        ax.annotate("Barbas en nudos (kt)", xy=(1, -0.2), xycoords="axes fraction", ha="right", fontsize=8,
                    color="#444444")
    return fig


def a_png(fig: Figure, dpi: int = 130) -> bytes:
    memoria = io.BytesIO()
    fig.savefig(memoria, format="png", dpi=dpi)
    return memoria.getvalue()
