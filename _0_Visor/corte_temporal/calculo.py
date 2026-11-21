"""Construcción de la sección tiempo x presión a partir del perfil de un punto."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import ConfigCorte, Vista

NUDOS_POR_MS = 1.94384449244          # las barbas siempre se dibujan en nudos


@dataclass(frozen=True)
class Seccion:
    horas: pd.DatetimeIndex            # UTC, sin zona (solo para graficar)
    niveles: np.ndarray                # hPa, de menor a mayor presión
    valores: np.ndarray                # (niveles, horas) en la unidad mostrada
    unidad: str
    u_nudos: np.ndarray | None = None  # solo para vistas con barbas
    v_nudos: np.ndarray | None = None

    def recortar(self, presion_superior: float, presion_inferior: float) -> Seccion:
        """Deja los niveles entre ``presion_superior`` (hPa, arriba) y ``presion_inferior`` (hPa, abajo)."""
        mascara = (self.niveles >= presion_superior) & (self.niveles <= presion_inferior)
        if mascara.sum() < 2:
            raise ValueError("El rango de presión elegido contiene menos de 2 niveles.")
        return Seccion(self.horas, self.niveles[mascara], self.valores[mascara], self.unidad,
                       None if self.u_nudos is None else self.u_nudos[mascara],
                       None if self.v_nudos is None else self.v_nudos[mascara])

    def a_tabla(self) -> pd.DataFrame:
        """Tabla niveles x horas (para exportar)."""
        columnas = [f"{h:%d/%m %H}Z" for h in self.horas]
        tabla = pd.DataFrame(self.valores[::-1], index=self.niveles[::-1], columns=columnas)
        tabla.index.name = "hPa"
        return tabla.round(2)


def _matriz(tabla: pd.DataFrame, prefijo: str) -> pd.DataFrame:
    """Niveles x horas de una capa (puede traer huecos como NaN)."""
    datos = tabla[tabla["Capa"] == prefijo]
    if datos.empty:
        raise ValueError(f"No hay datos de la capa '{prefijo}' para este punto.")
    matriz = datos.pivot_table(index="Nivel_hPa", columns="FechaHoraUTC", values="Valor", aggfunc="first")
    return matriz.sort_index().sort_index(axis=1)


def construir_seccion(tabla: pd.DataFrame, vista: Vista, unidad: str, cfg: ConfigCorte) -> Seccion:
    """Sección lista para graficar: convierte unidades y calcula la rapidez cuando corresponde."""
    parametros = vista.unidades[unidad]
    if vista.campo == "rapidez":
        u, v = _matriz(tabla, "u"), _matriz(tabla, "v")
        niveles = u.index.intersection(v.index)
        horas = u.columns.intersection(v.columns)
        if len(niveles) < 2 or len(horas) < 2:
            raise ValueError("No hay suficientes niveles u horas comunes entre u y v.")
        u, v = u.loc[niveles, horas], v.loc[niveles, horas]
        base = np.hypot(u.to_numpy(), v.to_numpy())
        u_nudos, v_nudos = u.to_numpy() * NUDOS_POR_MS, v.to_numpy() * NUDOS_POR_MS
        valores = base * parametros.factor + parametros.desplazamiento
    else:
        matriz = _matriz(tabla, vista.campo)
        niveles, horas = matriz.index, matriz.columns
        if len(niveles) < 2 or len(horas) < 2:
            raise ValueError("No hay suficientes niveles u horas para dibujar el corte.")
        valores = matriz.to_numpy() * parametros.factor + parametros.desplazamiento
        u_nudos = v_nudos = None
    return Seccion(pd.DatetimeIndex(horas).tz_convert("UTC").tz_localize(None), np.asarray(niveles, dtype=float),
                   valores, unidad, u_nudos, v_nudos)
