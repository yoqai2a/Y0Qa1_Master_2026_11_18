"""Escritura de un archivo NetCDF (forecast_hour × latitude × longitude)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .configuracion import Netcdf
from .variables import Capa


@dataclass
class InfoArchivo:
    """Lo que se sabe de un archivo ya terminado (alimenta el índice)."""
    ruta: Path
    bytes: int
    capas: list[Capa]
    minimos: dict[str, float]
    maximos: dict[str, float]
    horas_con_datos: dict[str, list[int]]


@dataclass
class ArchivoNC:
    destino: Path
    capas: list[Capa]
    leads: list[int]
    lat1d: np.ndarray
    lon1d: np.ndarray
    fecha: str
    ciclo: str
    opciones: Netcdf
    titulo: str
    atributos_globales: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        from netCDF4 import Dataset

        self.temporal = self.destino.with_name(self.destino.name + ".part")
        self.destino.parent.mkdir(parents=True, exist_ok=True)
        self.temporal.unlink(missing_ok=True)
        self.indice_lead = {lead: i for i, lead in enumerate(self.leads)}
        self.minimos: dict[str, float] = {}
        self.maximos: dict[str, float] = {}
        self.horas: dict[str, list[int]] = {c.nombre: [] for c in self.capas}
        self._ds = Dataset(str(self.temporal), "w", format="NETCDF4")
        self._crear_estructura()

    # ------------------------------------------------------------------
    def _crear_estructura(self) -> None:
        ds, o = self._ds, self.opciones
        ds.setncattr("title", self.titulo)
        ds.setncattr("model", "GFS")
        ds.setncattr("initialization_date", self.fecha)
        ds.setncattr("initialization_cycle_utc", f"{self.ciclo}Z")
        ds.setncattr("created_utc", datetime.now(timezone.utc).isoformat())
        for clave, valor in self.atributos_globales.items():
            ds.setncattr(clave, valor)

        ny, nx = len(self.lat1d), len(self.lon1d)
        ds.createDimension("forecast_hour", len(self.leads))
        ds.createDimension("latitude", ny)
        ds.createDimension("longitude", nx)
        lat = ds.createVariable("latitude", "f4", ("latitude",))
        lon = ds.createVariable("longitude", "f4", ("longitude",))
        lat[:], lon[:] = self.lat1d, self.lon1d
        lat.long_name, lat.units = "latitude", "degrees_north"
        lon.long_name, lon.units = "longitude", "degrees_east"
        horas = ds.createVariable("forecast_hour", "i2", ("forecast_hour",))
        horas.long_name, horas.units = "forecast lead time", "hours"
        horas[:] = self.leads
        valido = ds.createVariable("valid_time", "i4", ("forecast_hour",))
        valido.long_name = "valid time"
        valido.units = (f"hours since {self.fecha[:4]}-{self.fecha[4:6]}-{self.fecha[6:]} "
                        f"{int(self.ciclo):02d}:00:00 +00:00")
        valido.calendar = "standard"
        valido[:] = self.leads

        # (GranularBitRound: 'significant_digits' son dígitos decimales; en BitRound serían bits.)
        # Un mapa completo por bloque: el visor lee un cuadro de una sola vez.
        kwargs = dict(zlib=o.compresion > 0, shuffle=o.shuffle and o.compresion > 0,
                      chunksizes=(1, ny, nx), fill_value=np.float32("nan"))
        if o.compresion > 0:
            kwargs["complevel"] = o.compresion
        if o.cifras_significativas > 0:
            kwargs.update(significant_digits=o.cifras_significativas, quantize_mode="GranularBitRound")
        for capa in self.capas:
            try:
                var = ds.createVariable(capa.nombre, "f4", ("forecast_hour", "latitude", "longitude"), **kwargs)
            except TypeError as exc:  # netCDF4 < 1.6 sin 'quantize_mode'
                raise RuntimeError(
                    "cifras_significativas requiere netCDF4 >= 1.6 (pip install -U netCDF4)"
                ) from exc
            self._atributos(var, capa)

    @staticmethod
    def _atributos(var, c: Capa) -> None:
        atributos = {
            "long_name": c.long_name or None,
            "units": c.unidades or None,
            "GRIB_shortName": c.short_name,
            "GRIB_typeOfLevel": c.tipo_nivel,
            "GRIB_stepType": c.step_type,
            "GRIB_level": c.nivel,
            "GRIB_topLevel": c.top,
            "GRIB_bottomLevel": c.bottom,
            "classification": c.grupo,
        }
        for nombre, valor in atributos.items():
            if valor is not None:
                setattr(var, nombre, valor)

    # ------------------------------------------------------------------
    def escribir(self, lead: int, nombre: str, matriz: np.ndarray, minimo: float, maximo: float) -> None:
        self._ds.variables[nombre][self.indice_lead[lead], :, :] = matriz
        self.horas[nombre].append(lead)
        if np.isfinite(minimo):
            self.minimos[nombre] = min(self.minimos.get(nombre, minimo), minimo)
            self.maximos[nombre] = max(self.maximos.get(nombre, maximo), maximo)

    def cerrar(self) -> InfoArchivo:
        # Rango real de cada variable en todo el pronóstico: el visor lo usa como
        # escala automática. (No se llama valid_min/valid_max para que netCDF4 no
        # enmascare valores por redondeo.)
        for nombre, minimo in self.minimos.items():
            var = self._ds.variables[nombre]
            var.setncattr("data_min", np.float32(minimo))
            var.setncattr("data_max", np.float32(self.maximos[nombre]))
        self._ds.close()
        os.replace(self.temporal, self.destino)
        return InfoArchivo(self.destino, self.destino.stat().st_size, self.capas,
                           dict(self.minimos), dict(self.maximos),
                           {n: sorted(h) for n, h in self.horas.items()})

    def abortar(self) -> None:
        try:
            self._ds.close()
        except Exception:
            pass
        self.temporal.unlink(missing_ok=True)
