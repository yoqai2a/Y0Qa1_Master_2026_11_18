"""Conversión GRIB -> NetCDF por fases, con lectura de los fNNN en paralelo.

1. Escaneo (una vez): se ubica cada capa en cada fNNN, sin decodificar valores.
   Así se sabe de antemano qué variables existen y solo se crean esos archivos.
2. Pasadas por lotes: cada lote abre como mucho `archivos_simultaneos` .nc y lee
   de cada fNNN solo los mensajes de esas capas. Con la agrupación "capa" hay
   ~370 archivos, y mantenerlos todos abiertos agotaría el límite de descriptores.
"""
from __future__ import annotations

import multiprocessing
import time
from concurrent.futures import FIRST_COMPLETED, Executor, ProcessPoolExecutor, wait
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

from .configuracion import Config, procesos_efectivos
from .escritor import ArchivoNC, InfoArchivo
from .grib import (ContextoLectura, Escaneo, decodificar, escanear_lead, iniciar_trabajador,
                   leer_malla, tarea_decodificar, tarea_escanear)
from .plan import partir_en_lotes, planificar
from .variables import Capa, indexar


@dataclass
class ResultadoConversion:
    fecha: str
    ciclo: str
    leads: list[int]
    lat1d: Any
    lon1d: Any
    archivos: list[InfoArchivo]
    ausentes_siempre: list[str]                 # capas que no aparecieron en ningún fNNN
    duplicados: dict[str, list[int]] = field(default_factory=dict)   # capa -> horas con varios candidatos
    segundos: float = 0.0


def _ejecutar(
    ejecutor: Executor | None,
    tareas: Iterable[tuple[int, Callable, tuple, Callable, tuple]],
    ventana: int,
) -> Iterator[tuple[int, Any]]:
    """Resultados por lead. Cada tarea es (lead, función_en_proceso, args, función_local, args).

    Con ejecutor mantiene `ventana` tareas en vuelo, lo que acota la memoria
    (cada resultado de decodificación pesa varios MB).
    """
    if ejecutor is None:
        for lead, _, _, local, args in tareas:
            yield lead, local(*args)
        return
    pendientes: dict = {}
    iterador = iter(tareas)

    def enviar() -> None:
        try:
            lead, remota, args, _, _ = next(iterador)
        except StopIteration:
            return
        pendientes[ejecutor.submit(remota, *args)] = lead

    for _ in range(ventana):
        enviar()
    while pendientes:
        hechos, _ = wait(pendientes, return_when=FIRST_COMPLETED)
        for futuro in hechos:
            lead = pendientes.pop(futuro)
            yield lead, futuro.result()
            enviar()


def convertir(
    cfg: Config,
    capas: list[Capa],
    archivos_grib: list[tuple[int, Path]],
    fecha: str,
    ciclo: str,
    carpeta_salida: Path,
    log: Callable[[str], None] = print,
) -> ResultadoConversion:
    try:
        import netCDF4  # noqa: F401
        import numpy  # noqa: F401
        import pygrib  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("Faltan dependencias: pip install numpy netCDF4 pygrib "
                           "(pygrib: en Windows/macOS mejor 'conda install -c conda-forge pygrib').") from exc

    inicio = time.perf_counter()
    leads = [lead for lead, _ in archivos_grib]
    rutas = dict(archivos_grib)
    lat1d, lon1d = leer_malla(archivos_grib[0][1])
    ctx = ContextoLectura(indexar(capas), lat1d, lon1d)
    procesos = max(1, min(procesos_efectivos(cfg), len(leads)))
    log(f"Malla: {len(lat1d)} × {len(lon1d)} puntos; {len(leads)} horas (f{leads[0]:03d}–f{leads[-1]:03d}); "
        f"{len(capas)} variables configuradas; {procesos} proceso(s) de lectura")

    ejecutor = None
    if procesos > 1:
        # 'spawn': seguro con HDF5/netCDF4 abierto en este proceso y portable (Windows).
        ejecutor = ProcessPoolExecutor(
            max_workers=procesos, mp_context=multiprocessing.get_context("spawn"),
            initializer=iniciar_trabajador, initargs=(ctx,),
        )
    terminados: list[InfoArchivo] = []
    try:
        # ---- Fase 1: escaneo único de cada fNNN -------------------------------------
        escaneos: dict[int, Escaneo] = {}
        tareas = ((lead, tarea_escanear, (str(ruta),), escanear_lead, (ctx, ruta)) for lead, ruta in archivos_grib)
        for lead, escaneo in _ejecutar(ejecutor, tareas, procesos * 2):
            escaneos[lead] = escaneo
            if len(escaneos) % 20 == 0 or len(escaneos) == len(leads):
                log(f"  escaneo: {len(escaneos)}/{len(leads)} horas")
        presentes = {nombre for e in escaneos.values() for nombre in e.mapa}
        ausentes = [c.nombre for c in capas if c.nombre not in presentes]
        activas = [c for c in capas if c.nombre in presentes]
        duplicados: dict[str, list[int]] = {}
        for lead in leads:
            for nombre in escaneos[lead].duplicados:
                duplicados.setdefault(nombre, []).append(lead)
        if not activas:
            raise RuntimeError("Ninguna de las variables configuradas está en los GRIB.")

        # ---- Fase 2: pasadas por lotes ----------------------------------------------
        # Si una capa no aparece en el primer lead, usa el primer lead donde exista.
        mensajes: dict[str, int] = {}
        for lead in leads:
            for nombre, msg in escaneos[lead].mensajes.items():
                mensajes.setdefault(nombre, msg)
        plan = planificar(activas, cfg.salida.agrupacion, cfg.salida.prefijo, fecha, ciclo, mensajes)
        lotes = partir_en_lotes(plan, cfg.netcdf.archivos_simultaneos)
        log(f"Agrupación '{cfg.salida.agrupacion}': {len(plan)} archivos con {len(activas)} variables "
            f"en {len(lotes)} pasada(s)")

        for n_lote, lote in enumerate(lotes, 1):
            abiertos: dict[str, ArchivoNC] = {}
            destino_de: dict[str, ArchivoNC] = {}
            try:
                for nombre_archivo, grupo in lote.items():
                    archivo = ArchivoNC(
                        destino=carpeta_salida / nombre_archivo, capas=grupo, leads=leads,
                        lat1d=lat1d, lon1d=lon1d, fecha=fecha, ciclo=ciclo, opciones=cfg.netcdf,
                        titulo=f"GFS {fecha} {ciclo}Z · {nombre_archivo[:-3].split('Z_', 1)[-1]}",
                        atributos_globales={
                            "grouping": cfg.salida.agrupacion,
                            "source_directory": str(archivos_grib[0][1].parent),
                        },
                    )
                    abiertos[nombre_archivo] = archivo
                    for capa in grupo:
                        destino_de[capa.nombre] = archivo

                def tareas_lote() -> Iterator:
                    for lead in leads:
                        seleccion = {n: escaneos[lead].mapa[n] for n in destino_de if n in escaneos[lead].mapa}
                        if seleccion:
                            ruta = rutas[lead]
                            yield (lead, tarea_decodificar, (str(ruta), seleccion),
                                   decodificar, (ctx, ruta, seleccion))

                hechos = 0
                for lead, campos in _ejecutar(ejecutor, tareas_lote(), procesos * 2):
                    for nombre, (matriz, minimo, maximo) in campos.items():
                        destino_de[nombre].escribir(lead, nombre, matriz, minimo, maximo)
                    hechos += 1
                    if hechos % 30 == 0:
                        log(f"  pasada {n_lote}/{len(lotes)}: {hechos}/{len(leads)} horas")
                for archivo in abiertos.values():
                    terminados.append(archivo.cerrar())
                abiertos.clear()
                log(f"  pasada {n_lote}/{len(lotes)} terminada ({len(lote)} archivos)")
            except BaseException:
                for archivo in abiertos.values():
                    archivo.abortar()
                raise
    finally:
        if ejecutor is not None:
            ejecutor.shutdown(wait=True, cancel_futures=True)

    return ResultadoConversion(fecha, ciclo, leads, lat1d, lon1d, terminados, ausentes, duplicados,
                               time.perf_counter() - inicio)
