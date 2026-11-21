"""Descarga paralela de fNNN, validación de GRIB y limpieza por retención."""
from __future__ import annotations

import fnmatch
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests

from .configuracion import Descarga

BLOQUE = 1024 * 1024
PATRONES_LIMPIEZA = (
    "gfs.t??z.pgrb2.*.f[0-9][0-9][0-9]",
    "gfs.t??z.pgrb2.*.f[0-9][0-9][0-9].part",
    "gfs.t??z.pgrb2.*.f[0-9][0-9][0-9].json",
    "gfs.t??z.pgrb2.*.f[0-9][0-9][0-9].json.tmp",
    "Listado_Variables.json",
    "Listado_Variables.json.tmp",
)


@dataclass(frozen=True)
class Resultado:
    nombre: str
    ok: bool
    mensaje: str
    bytes: int = 0


class _RespuestaInvalida(Exception):
    """El servidor respondió 200 pero con algo que no es un GRIB (p. ej. HTML de error)."""


def grib_valido(ruta: Path, minimo: int) -> bool:
    """Comprueba tamaño mínimo, cabecera 'GRIB' y cierre '7777'."""
    try:
        if ruta.stat().st_size < minimo:
            return False
        with ruta.open("rb") as archivo:
            if archivo.read(4) != b"GRIB":
                return False
            archivo.seek(-4, 2)
            return archivo.read(4) == b"7777"
    except (OSError, ValueError):
        return False


def _espera_servidor(respuesta: requests.Response) -> float:
    try:
        return min(float(respuesta.headers.get("Retry-After", 0)), 60.0)
    except ValueError:
        return 0.0


def descargar_uno(
    sesion: requests.Session, nombre: str, url: str, carpeta: Path, opc: Descarga
) -> Resultado:
    destino = carpeta / nombre
    temporal = carpeta / f"{nombre}.part"
    if grib_valido(destino, opc.tamano_minimo_bytes):
        return Resultado(nombre, True, "ya existe y es válido", destino.stat().st_size)
    destino.unlink(missing_ok=True)

    ultimo_error = "respuesta inválida"
    for intento in range(1, opc.reintentos + 1):
        espera = opc.espera_reintento_s * intento + random.uniform(0, 0.5)
        try:
            with sesion.get(url, stream=True,
                            timeout=(opc.timeout_conexion_s, opc.timeout_lectura_s)) as resp:
                if resp.status_code in (429, 503):
                    espera = max(espera, _espera_servidor(resp))
                resp.raise_for_status()
                bloques = resp.iter_content(BLOQUE)
                primero = next(bloques, b"")
                if not primero.startswith(b"GRIB"):
                    # Corta de inmediato: no se escribe a disco una página de error.
                    muestra = primero[:150].decode("utf-8", "replace").replace("\n", " ")
                    raise _RespuestaInvalida(f"respuesta no GRIB: {muestra}")
                with temporal.open("wb") as archivo:
                    archivo.write(primero)
                    for bloque in bloques:
                        archivo.write(bloque)
            if grib_valido(temporal, opc.tamano_minimo_bytes):
                tamano = temporal.stat().st_size
                temporal.replace(destino)
                return Resultado(nombre, True, f"descargado (intento {intento})", tamano)
            ultimo_error = "archivo incompleto (sin cierre 7777 o demasiado pequeño)"
        except _RespuestaInvalida as exc:
            ultimo_error = str(exc)
        except (requests.RequestException, OSError) as exc:
            ultimo_error = str(exc)
        temporal.unlink(missing_ok=True)
        if intento < opc.reintentos:
            time.sleep(espera)
    return Resultado(nombre, False, ultimo_error)


def descargar_todo(
    sesion: requests.Session,
    urls: list[tuple[str, str]],
    carpeta: Path,
    opc: Descarga,
    al_terminar: Callable[[int, int, Resultado], None] | None = None,
) -> list[Resultado]:
    """Descarga en paralelo; `al_terminar(n, total, resultado)` informa el progreso."""
    resultados: list[Resultado] = []
    pool = ThreadPoolExecutor(max_workers=max(1, min(opc.conexiones, len(urls))))
    try:
        trabajos = [pool.submit(descargar_uno, sesion, n, u, carpeta, opc) for n, u in urls]
        for n, futuro in enumerate(as_completed(trabajos), 1):
            resultado = futuro.result()
            resultados.append(resultado)
            if al_terminar:
                al_terminar(n, len(urls), resultado)
    finally:
        # Ctrl+C: no deja encolados los trabajos pendientes.
        pool.shutdown(wait=True, cancel_futures=True)
    return resultados


def limpiar_antiguos(carpeta: Path, retencion_horas: float) -> int:
    """Borra solo GRIB y temporales producidos aquí que excedan la retención.

    También elimina las carpetas fecha/ciclo que queden vacías.
    """
    if not carpeta.exists():
        return 0
    limite = time.time() - retencion_horas * 3600
    borrados = 0
    for ruta in carpeta.rglob("*"):
        if (ruta.is_file() and not ruta.is_symlink()
                and any(fnmatch.fnmatch(ruta.name, p) for p in PATRONES_LIMPIEZA)
                and ruta.stat().st_mtime < limite):
            ruta.unlink()
            borrados += 1
    for sub in sorted((p for p in carpeta.rglob("*") if p.is_dir()), reverse=True):
        try:
            sub.rmdir()  # solo prospera si está vacía
        except OSError:
            pass
    print(f"Limpieza de retención: {borrados} GRIB antiguos eliminados.")
    return borrados
