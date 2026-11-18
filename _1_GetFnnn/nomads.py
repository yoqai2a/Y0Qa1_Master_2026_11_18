"""Acceso a NOMADS: sesión HTTP, nombres de archivo y URLs del filtro."""
from __future__ import annotations

import re

import requests
from requests.adapters import HTTPAdapter

from .conjuntos import construir_seleccion
from .configuracion import Config

USER_AGENT = "Y0QA1-GFS-downloader/2.0"


def crear_sesion(conexiones: int) -> requests.Session:
    """Sesión con un pool tan grande como el número de hilos.

    El pool por defecto de requests es de 10 conexiones: con 32 hilos las
    sobrantes se abren y se descartan en cada petición (y urllib3 avisa
    'Connection pool is full'), lo que desperdicia el handshake TLS.
    """
    sesion = requests.Session()
    sesion.headers.update({"User-Agent": USER_AGENT})
    adaptador = HTTPAdapter(pool_connections=4, pool_maxsize=max(conexiones, 10), max_retries=0)
    sesion.mount("https://", adaptador)
    sesion.mount("http://", adaptador)
    return sesion


def nombre_archivo(ciclo: str, resolucion: str, lead: int) -> str:
    return f"gfs.t{ciclo}z.pgrb2.{resolucion}.f{lead:03d}"


def lead_de_nombre(nombre: str) -> int:
    coincidencia = re.search(r"\.f(\d{3})$", nombre)
    if coincidencia is None:
        raise ValueError(f"Nombre sin sufijo fNNN: {nombre}")
    return int(coincidencia.group(1))


def url_directorio_ciclo(cfg: Config, fecha: str, ciclo: str) -> str:
    return f"{cfg.modelo.url_prod}/gfs.{fecha}/{ciclo}/atmos/"


def construir_urls(
    cfg: Config,
    fecha: str,
    ciclo: str,
    leads: list[int],
    publicados: set[int] | None,
) -> list[tuple[str, str]]:
    """Pares (nombre, url) del filtro NOMADS para los leads pedidos.

    Si se conoce el listado `publicados`, descarta los leads aún inexistentes.
    """
    modelo, area = cfg.modelo, cfg.area
    seleccion = construir_seleccion(cfg.conjunto, modelo.parametros_extra)
    base = f"{modelo.url_base}/filter_gfs_{modelo.resolucion}.pl"
    if publicados is not None:
        leads = [h for h in leads if h in publicados]
    urls = []
    for lead in leads:
        nombre = nombre_archivo(ciclo, modelo.resolucion, lead)
        consulta = (
            f"dir=%2Fgfs.{fecha}%2F{ciclo}%2Fatmos&file={nombre}&{seleccion}"
            f"&subregion=&toplat={area.norte}&leftlon={area.oeste}"
            f"&rightlon={area.este}&bottomlat={area.sur}"
        )
        urls.append((nombre, f"{base}?{consulta}"))
    return urls
