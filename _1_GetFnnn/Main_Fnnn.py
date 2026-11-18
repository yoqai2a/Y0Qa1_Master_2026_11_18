"""Orquestador de la descarga de fNNN de GFS (se inicia desde _1_YoQai.py).

Uso (desde la raíz del proyecto):
    python _1_YoQai.py                           # interactivo: propone el último ciclo
    python _1_YoQai.py --sin-preguntas           # acepta el último ciclo disponible
    python _1_YoQai.py --fecha 20261104 --ciclo 12
    python _1_YoQai.py --conjunto XyGrib --simular
    python _1_YoQai.py --area SCGU --conjunto XyGrib
    python _1_YoQai.py --crear-nc                # descarga y convierte; deja solo los .nc
    python _1_YoQai.py --solo-fnnn               # descarga y conserva los fNNN
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from . import ci
from .ciclos import elegir_ciclo, horas_pronostico
from .configuracion import ErrorConfiguracion, cargar_configuracion
from .control import ciclo_creado
from .descarga import Resultado, descargar_todo, limpiar_antiguos
from .nomads import construir_urls, crear_sesion, lead_de_nombre
from .utilidades import ahora_utc, duracion, imprimir_marca, tamano_legible

CARPETA_MODULO = Path(__file__).resolve().parent
RAIZ_PROYECTO = CARPETA_MODULO.parent
CONFIG_DEFECTO = CARPETA_MODULO / "__Configuracion_Fnnn.toml"


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Descarga fNNN de GFS desde NOMADS")
    p.add_argument("--config", type=Path, default=CONFIG_DEFECTO, help="Ruta del archivo .toml")
    p.add_argument("--fecha", help="Fecha del ciclo GFS en formato AAAAMMDD")
    p.add_argument("--ciclo", choices=("00", "06", "12", "18"), help="Ciclo GFS en UTC")
    p.add_argument("--conjunto", help="Conjunto de variables (sustituye al del .toml)")
    p.add_argument("--area", help="Área geográfica (sustituye a modelo.area del .toml)")
    flujo = p.add_mutually_exclusive_group()
    flujo.add_argument("--crear-nc", dest="crear_nc", action="store_true", default=None,
                       help="Tras descargar, ejecuta _2_CreaNC (sustituye a [flujo] crear_nc)")
    flujo.add_argument("--solo-fnnn", dest="crear_nc", action="store_false",
                       help="Solo descarga y conserva los fNNN (sustituye a [flujo] crear_nc)")
    p.add_argument("--sin-preguntas", action="store_true",
                   help="Acepta automáticamente el último ciclo disponible")
    p.add_argument("--forzar", action="store_true",
                   help="Descarga de nuevo aunque control.xlsx indique que el ciclo ya existe")
    p.add_argument("--simular", action="store_true",
                   help="Muestra qué se descargaría, sin descargar nada")
    return p


def _resumen_ci(fecha, ciclo, cfg, resultados: list[Resultado], segundos: float) -> None:
    ok = [r for r in resultados if r.ok]
    fallos = [r for r in resultados if not r.ok]
    lineas = [
        f"### GFS {fecha} {ciclo}Z — {cfg.modelo.resolucion} / {cfg.modelo.conjunto} / {cfg.area.nombre}",
        "",
        f"- Archivos correctos: **{len(ok)}/{len(resultados)}**",
        f"- Tamaño total: **{tamano_legible(sum(r.bytes for r in ok))}**",
        f"- Duración de la descarga: {duracion(segundos)}",
    ]
    if fallos:
        lineas += ["", "**Con error:**", ""]
        lineas += [f"- `{r.nombre}`: {r.mensaje}" for r in sorted(fallos, key=lambda r: r.nombre)]
    ci.escribir_resumen("\n".join(lineas))


def _continuar_con_crea_nc(carpeta: Path) -> int:
    """Ejecuta _2_CreaNC sobre el ciclo descargado (importa el módulo solo si hace falta)."""
    try:
        from _2_CreaNC.Main_NC import main as main_nc
    except ImportError as exc:
        print(f"No se pudo cargar _2_CreaNC: {exc}", file=sys.stderr)
        ci.anotar("error", f"No se pudo cargar _2_CreaNC: {exc}")
        return 2
    print("Continuando con _2_CreaNC...", flush=True)
    codigo = main_nc([str(carpeta)])
    if codigo != 0:
        ci.anotar("error", "La creación de NetCDF falló; los fNNN se conservan")
    return codigo


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    inicio_programa = time.perf_counter()
    print(f"Inicio del programa: {ahora_utc()}", flush=True)
    sesion = None
    try:
        cfg = cargar_configuracion(args.config, RAIZ_PROYECTO, args.conjunto, args.area, args.crear_nc)
        ruta_control = cfg.descarga.carpeta_salida.parent / "control.xlsx"
        if args.fecha and args.ciclo and not args.forzar and ciclo_creado(ruta_control, args.fecha, args.ciclo):
            print(f"El ciclo {args.fecha} {args.ciclo}Z ya existe en control.xlsx; se omite la descarga.")
            return 0
        sesion = crear_sesion(cfg.descarga.conexiones)
        # Sin terminal (CI, cron, tubería) input() bloquearía o fallaría.
        interactivo = not (args.sin_preguntas or ci.en_ci() or not sys.stdin.isatty())
        fecha, ciclo, publicados = elegir_ciclo(
            sesion, cfg, args.fecha, args.ciclo, interactivo=interactivo
        )

        if not args.forzar and ciclo_creado(ruta_control, fecha, ciclo):
            print(f"El ciclo {fecha} {ciclo}Z ya existe en control.xlsx; se omite la descarga.")
            return 0

        raiz_datos = cfg.descarga.carpeta_salida
        carpeta = raiz_datos / fecha / ciclo
        limpiar_antiguos(raiz_datos, cfg.descarga.retencion_horas)

        leads = horas_pronostico(cfg.modelo, ciclo)
        urls = construir_urls(cfg, fecha, ciclo, leads, publicados)
        if not urls:
            print("No hay pasos de pronóstico configurados disponibles en NOMADS para ese ciclo.")
            ci.anotar("error", f"Sin fNNN disponibles para {fecha} {ciclo}Z")
            return 1
        disponibles = [lead_de_nombre(n) for n, _ in urls]
        print(f"Descarga: {fecha} {ciclo}Z; f{min(disponibles):03d}–f{max(disponibles):03d}; "
              f"{len(urls)} archivos disponibles (conjunto {cfg.modelo.conjunto}, "
              f"área {cfg.area.nombre}: N{cfg.area.norte} S{cfg.area.sur} "
              f"O{cfg.area.oeste} E{cfg.area.este})")
        print(f"Salida: {carpeta}")
        print("Flujo: descarga -> CREA_NC (al terminar se borran los fNNN)" if cfg.flujo.crear_nc
              else "Flujo: solo descarga (crear_nc = false); CREA_NC NO se ejecutará "
                   "(usa --crear-nc o [flujo] crear_nc = true)")
        if len(urls) < len(leads):
            ci.anotar("warning", f"Ciclo {fecha} {ciclo}Z parcial: {len(urls)}/{len(leads)} fNNN publicados")
        if args.simular:
            print("Modo simulación: no se descarga nada.")
            return 0

        carpeta.mkdir(parents=True, exist_ok=True)
        ci.exportar_salidas(fecha=fecha, ciclo=ciclo, carpeta=str(carpeta))

        def progreso(n: int, total: int, r: Resultado) -> None:
            print(f"[{n}/{total}] {'OK' if r.ok else 'ERROR'} {r.nombre}: {r.mensaje}", flush=True)

        inicio_descarga = time.perf_counter()
        print(f"Inicio de descarga: {ahora_utc()}", flush=True)
        try:
            resultados = descargar_todo(sesion, urls, carpeta, cfg.descarga, progreso)
        finally:
            imprimir_marca("Fin de descarga", inicio_descarga, inicio_programa)

        errores = [r for r in resultados if not r.ok]
        print(f"Finalizado: {len(resultados) - len(errores)}/{len(resultados)} correctos; "
              f"{len(errores)} errores")
        _resumen_ci(fecha, ciclo, cfg, resultados, time.perf_counter() - inicio_descarga)
        for r in errores:
            ci.anotar("error", f"{r.nombre}: {r.mensaje}")
        if errores:
            if cfg.flujo.crear_nc:
                print("No se crean los .nc: la descarga tiene errores. Los fNNN se conservan.")
            return 1
        if cfg.flujo.crear_nc:
            return _continuar_con_crea_nc(carpeta)
        print(f"Solo descarga: fNNN guardados en {carpeta}")
        return 0
    except KeyboardInterrupt:
        print("Interrumpido por el usuario.", file=sys.stderr)
        return 130
    except (ErrorConfiguracion, OSError, ValueError, KeyError, RuntimeError) as exc:
        print(f"Error de configuración/descarga: {exc}", file=sys.stderr)
        ci.anotar("error", str(exc))
        return 2
    finally:
        if sesion is not None:
            sesion.close()
        imprimir_marca("Fin del programa", inicio_programa, inicio_programa)

