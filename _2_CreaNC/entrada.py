"""Localiza la carpeta AAAAMMDD/HH con los fNNN y lista sus archivos GRIB."""
from __future__ import annotations

import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)

_RE_FECHA = re.compile(r"\d{8}")
CICLOS = ("00", "06", "12", "18")
_RE_NOMBRE = re.compile(r"^gfs\.t(\d{2})z\.pgrb2\.(\w+)\.f(\d{3})$")
TAMANO_MINIMO = 2000


def grib_valido(ruta: Path, minimo: int = TAMANO_MINIMO) -> bool:
    """Cabecera 'GRIB' y cierre '7777': descarta descargas truncadas."""
    try:
        if ruta.stat().st_size < minimo:
            return False
        with ruta.open("rb") as f:
            if f.read(4) != b"GRIB":
                return False
            f.seek(-4, 2)
            return f.read(4) == b"7777"
    except OSError:
        return False


def listar_grib(carpeta: Path, resolucion: str = "auto") -> list[tuple[int, Path]]:
    """[(lead, ruta)] ordenado. Ignora archivos truncados (con aviso)."""
    encontrados: dict[str, list[tuple[int, Path]]] = {}
    for ruta in carpeta.iterdir():
        m = _RE_NOMBRE.match(ruta.name)
        if m and ruta.is_file():
            encontrados.setdefault(m.group(2), []).append((int(m.group(3)), ruta))
    if resolucion != "auto":
        encontrados = {k: v for k, v in encontrados.items() if k == resolucion}
    if not encontrados:
        raise FileNotFoundError(f"No hay GRIB fNNN en {carpeta}")
    if len(encontrados) > 1:
        raise ValueError(
            f"{carpeta} mezcla resoluciones ({', '.join(sorted(encontrados))}): "
            "indica 'resolucion' en [entrada] del .toml."
        )
    archivos = sorted(next(iter(encontrados.values())), key=lambda x: x[0])
    validos = []
    for lead, ruta in archivos:
        if grib_valido(ruta):
            validos.append((lead, ruta))
        else:
            log.warning(f"AVISO: {ruta.name} está incompleto o dañado; se omite.")
    if not validos:
        raise FileNotFoundError(f"Ningún GRIB válido en {carpeta}")
    return validos


def eliminar_fnnn(carpeta: Path) -> int:
    """Borra los fNNN (y sus .part/.idx) de un ciclo ya convertido a NetCDF.

    Solo toca archivos con nombre gfs.tHHz.pgrb2.<res>.fNNN; cualquier otro
    archivo se respeta. Quita la carpeta del ciclo y la del día si quedan vacías.
    """
    borrados = 0
    for ruta in carpeta.iterdir():
        base = re.sub(r"\.(part|idx)$", "", ruta.name)
        if ruta.is_file() and not ruta.is_symlink() and _RE_NOMBRE.match(base):
            ruta.unlink()
            borrados += 1
    for vacia in (carpeta, carpeta.parent):
        try:
            vacia.rmdir()
        except OSError:
            pass
    return borrados


def validar_carpeta_ciclo(carpeta: Path) -> tuple[str, str]:
    """Comprueba que sea .../AAAAMMDD/HH y devuelve (fecha, ciclo)."""
    fecha, ciclo = carpeta.parent.name, carpeta.name
    if not _RE_FECHA.fullmatch(fecha) or ciclo not in CICLOS:
        raise ValueError(f"Se esperaba una carpeta .../AAAAMMDD/HH, recibí: {carpeta}")
    return fecha, ciclo


def ciclo_mas_reciente(raiz: Path) -> Path:
    """Carpeta AAAAMMDD/HH más reciente que contenga fNNN."""
    if not raiz.is_dir():
        raise FileNotFoundError(f"No existe la carpeta de fNNN: {raiz}")
    candidatas = []
    for dia in raiz.iterdir():
        if dia.is_dir() and _RE_FECHA.fullmatch(dia.name):
            for ciclo in dia.iterdir():
                if ciclo.is_dir() and ciclo.name in CICLOS and any(
                    _RE_NOMBRE.match(p.name) for p in ciclo.iterdir()
                ):
                    candidatas.append((dia.name, ciclo.name, ciclo))
    if not candidatas:
        raise FileNotFoundError(f"No hay ciclos con fNNN en {raiz}")
    return max(candidatas)[2]


def resolver_carpeta(raiz_fnnn: Path, carpeta: Path | None, fecha: str | None, ciclo: str | None) -> Path:
    if carpeta is not None:
        return Path(carpeta).resolve()
    if bool(fecha) != bool(ciclo):
        raise ValueError("Para elegir un ciclo debes indicar fecha y ciclo.")
    if fecha and ciclo:
        ruta = raiz_fnnn / fecha / ciclo
        if not ruta.is_dir():
            raise FileNotFoundError(f"No existe {ruta}")
        return ruta
    return ciclo_mas_reciente(raiz_fnnn)
