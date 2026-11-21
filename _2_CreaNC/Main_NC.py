"""Orquestador de la creación de NetCDF (se inicia desde _2_Y0Qa1_CreaNC.py).

Uso (desde la raíz del proyecto):
    python _2_Y0Qa1_CreaNC.py                                  # ciclo más reciente de ___Data/___Fnnn
    python _2_Y0Qa1_CreaNC.py --fecha 20261106 --ciclo 12
    python _2_Y0Qa1_CreaNC.py "ruta/___Fnnn/20261106/12"       # carpeta concreta
    python _2_Y0Qa1_CreaNC.py --agrupacion variable --grupos Main --procesos 4
    python _2_Y0Qa1_CreaNC.py --simular                         # muestra el plan sin escribir
    python _2_Y0Qa1_CreaNC.py --inventario ruta/gfs.t12z.pgrb2.0p25.f012
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

from _Comun.registro import configurar as configurar_logging

from .configuracion import ErrorConfiguracion, cargar_configuracion, procesos_efectivos
from .conversion import convertir
from .entrada import eliminar_fnnn, listar_grib, resolver_carpeta, validar_carpeta_ciclo
from .plan import planificar
from .salida import escribir_control, escribir_indice, escribir_ultimo, limpiar_ciclos
from .utilidades import ahora_utc, duracion, tamano_legible
from .variables import ErrorVariables, cargar_variables

log = logging.getLogger(__name__)

CARPETA_MODULO = Path(__file__).resolve().parent
RAIZ_PROYECTO = CARPETA_MODULO.parent
CONFIG_DEFECTO = CARPETA_MODULO / "__Configuracion_NC.toml"
VARIABLES_DEFECTO = CARPETA_MODULO / "__Variables_NC.toml"
SELECCION_DEFECTO = CARPETA_MODULO / "seleccion_nc.json"


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Crea NetCDF desde los fNNN de GFS")
    p.add_argument("carpeta_grib", nargs="?", type=Path,
                   help="Carpeta .../AAAAMMDD/HH con los fNNN (def.: el ciclo más reciente)")
    p.add_argument("--fecha", help="Fecha AAAAMMDD dentro de carpeta_fnnn")
    p.add_argument("--ciclo", choices=("00", "06", "12", "18"), help="Ciclo UTC")
    p.add_argument("--config", type=Path, default=CONFIG_DEFECTO, help="__Configuracion_NC.toml")
    p.add_argument("--variables", type=Path, default=VARIABLES_DEFECTO, help="__Variables_NC.toml")
    p.add_argument("--seleccion-nc", type=Path, default=SELECCION_DEFECTO,
                   help="JSON que decide qué archivos NetCDF se generan")
    p.add_argument("--agrupacion", choices=("capa", "variable", "grupo", "unico"),
                   help="Sustituye a [salida] agrupacion")
    p.add_argument("--grupos", nargs="+", help="Sustituye a [salida] grupos (ej.: Main)")
    p.add_argument("--procesos", type=int, help="Procesos de lectura (0 = automático)")
    p.add_argument("--compresion", type=int, help="Nivel zlib 0-9")
    p.add_argument("--conservar-fnnn", action="store_true",
                   help="No borra los fNNN tras convertir (sustituye a [entrada] eliminar_fnnn)")
    p.add_argument("--simular", action="store_true", help="Muestra el plan sin escribir nada")
    p.add_argument("--inventario", type=Path, metavar="GRIB",
                   help="Lista los mensajes de un fNNN (para añadir variables al .toml)")
    return p


def _mostrar_inventario(ruta: Path) -> None:
    from .grib import inventario
    print("msg\tshortName\ttipoNivel\tlevel\ttop\tbottom\tstepType\tstepRange\tparametro\tnombre\tunidades")
    for f in inventario(ruta):
        print("\t".join(str(f[k]) for k in ("msg", "shortName", "tipoNivel", "level", "top", "bottom",
                                          "stepType", "stepRange", "parametro", "name", "units")))


def main(argv: list[str] | None = None) -> int:
    configurar_logging()
    args = _parser().parse_args(argv)
    inicio = time.perf_counter()
    try:
        if args.inventario:
            _mostrar_inventario(args.inventario)
            return 0
        log.info(f"Inicio del programa: {ahora_utc()}")
        cfg = cargar_configuracion(args.config, RAIZ_PROYECTO, args.agrupacion, args.grupos,
                                   args.procesos, args.compresion,
                                   False if args.conservar_fnnn else None)
        todas = cargar_variables(args.variables)
        capas = [c for c in todas if c.grupo in cfg.salida.grupos]
        if not capas:
            grupos = sorted({c.grupo for c in todas})
            raise ErrorVariables(f"Ninguna variable pertenece a los grupos {list(cfg.salida.grupos)} "
                                 f"(el .toml tiene: {grupos}).")
        try:
            seleccion = json.loads(args.seleccion_nc.read_text(encoding="utf-8-sig"))["archivos"]
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ErrorVariables(f"No se pudo leer la selección NetCDF {args.seleccion_nc}: {exc}") from exc
        if not isinstance(seleccion, dict) or any(not isinstance(v, bool) for v in seleccion.values()):
            raise ErrorVariables(f"{args.seleccion_nc}: 'archivos' debe ser un objeto con valores true/false.")
        nombres_disponibles = {c.nombre for c in capas}
        desconocidos = sorted(k for k, v in seleccion.items() if v and k not in nombres_disponibles)
        if desconocidos:
            raise ErrorVariables("La selección activa contiene nombres que no están en __Variables_NC.toml: "
                                 + ", ".join(desconocidos[:8]))
        capas = [c for c in capas if seleccion.get(c.nombre, False)]
        if not capas:
            raise ErrorVariables(f"{args.seleccion_nc}: no hay archivos NetCDF seleccionados.")

        carpeta = resolver_carpeta(cfg.entrada.carpeta_fnnn, args.carpeta_grib, args.fecha, args.ciclo)
        fecha, ciclo = validar_carpeta_ciclo(carpeta)
        archivos = listar_grib(carpeta, cfg.entrada.resolucion)
        log.info(f"Entrada: {carpeta} ({len(archivos)} fNNN: f{archivos[0][0]:03d}–f{archivos[-1][0]:03d})")
        directorio = cfg.salida.carpeta_salida / fecha / ciclo
        log.info(f"Salida: {directorio}")

        if args.simular:
            plan = planificar(capas, cfg.salida.agrupacion, cfg.salida.prefijo, fecha, ciclo)
            log.info(f"Modo simulación: {len(capas)} variables en {len(plan)} archivo(s) "
                  f"('{cfg.salida.agrupacion}'), {procesos_efectivos(cfg)} proceso(s).")
            for nombre, grupo in list(plan.items())[:8]:
                log.info(f"  {nombre}  ({len(grupo)} variable(s))")
            if len(plan) > 8:
                log.info(f"  ... y {len(plan) - 8} más")
            return 0

        res = convertir(cfg, capas, archivos, fecha, ciclo, directorio)
        ruta_indice = escribir_indice(res, directorio, cfg.salida.agrupacion)
        ruta_control = escribir_control(cfg.salida.carpeta_salida.parent, res)
        escribir_ultimo(cfg.salida.carpeta_salida, res)
        borrados = limpiar_ciclos(cfg.salida.carpeta_salida, cfg.salida.conservar_ciclos, (fecha, ciclo))

        total = sum(i.bytes for i in res.archivos)
        log.info(f"NetCDF creados: {len(res.archivos)} archivo(s), {tamano_legible(total)} en total "
              f"(el mayor: {tamano_legible(max(i.bytes for i in res.archivos))})")
        log.info(f"Índice: {ruta_indice}")
        log.info(f"Control de ciclos: {ruta_control}")
        if borrados:
            log.info(f"Limpieza: {borrados} archivo(s) de ciclos antiguos eliminados.")
        for nombre, horas in sorted(res.duplicados.items()):
            lista = ", ".join(f"f{h:03d}" for h in horas[:4]) + ("..." if len(horas) > 4 else "")
            log.info(f"Duplicados: {nombre} tenía varios mensajes candidatos en {len(horas)} hora(s) "
                  f"({lista}); se aplicó la política 'duplicados' del campo.")
        if res.ausentes_siempre:
            muestra = ", ".join(res.ausentes_siempre[:6]) + ("..." if len(res.ausentes_siempre) > 6 else "")
            log.warning(f"AVISO: {len(res.ausentes_siempre)} variable(s) no están en ningún fNNN y no se escribieron "
                  f"({muestra}). ¿Se descargó un conjunto que no las incluye?")
        log.info(f"Duración de la conversión: {duracion(res.segundos)}")
        # Solo se llega aquí si la conversión terminó sin excepción.
        if cfg.entrada.eliminar_fnnn:
            log.info(f"fNNN eliminados de {carpeta}: {eliminar_fnnn(carpeta)} archivo(s); solo quedan los .nc.")
        else:
            log.info(f"fNNN conservados en {carpeta}.")
        return 0
    except KeyboardInterrupt:
        log.warning("Interrumpido por el usuario.")
        return 130
    except (ErrorConfiguracion, ErrorVariables, OSError, ValueError, RuntimeError) as exc:
        log.error(f"Error al crear NetCDF: {exc}")
        return 2
    finally:
        log.info(f"Fin del programa: {ahora_utc()} | desde el inicio: {duracion(time.perf_counter() - inicio)}")
