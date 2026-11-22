"""Ciclos GFS: horas de pronóstico (fNNN), consulta de NOMADS y elección del ciclo."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

import requests

from .configuracion import Config, Modelo
from .nomads import url_directorio_ciclo

log = logging.getLogger(__name__)

CICLOS = ("18", "12", "06", "00")  # de más reciente a más antiguo dentro de un día
_RE_FECHAS = re.compile(r"gfs\.(\d{8})/")
_RE_FECHA_CICLO = re.compile(r"(\d{8})\s+(00|06|12|18)")


# ----------------------------------------------------------------------------
# Horas de pronóstico
# ----------------------------------------------------------------------------
def horas_pronostico(modelo: Modelo, ciclo: str) -> list[int]:
    """Genera los leads según cierres diarios a las 03Z.

    Los días 0, 1 y 2 (por defecto) son horarios hasta el cierre local del
    día 2. Luego avanza de 3 en 3. El horizonte termina como máximo al cierre
    local del día 7. El lead se cuenta desde el ciclo de inicialización UTC.
    """
    hora_ciclo = int(ciclo)
    cierre_fino = modelo.dias_horarios * 24 + 3 - hora_ciclo
    cierre_final = modelo.dias_maximos * 24 + 3 - hora_ciclo
    # Antes de f120 admite pasos horarios. En f120 y después, siempre cada 3 h.
    cierre_fino = min(cierre_fino, 119, cierre_final)
    finos = list(range(0, cierre_fino + 1, modelo.paso_fino_horas))
    inicio_trihorario = cierre_fino + 1
    inicio_trihorario += (-inicio_trihorario) % 3
    trihorarios = list(range(inicio_trihorario, cierre_final + 1, 3))
    return finos + trihorarios


# ----------------------------------------------------------------------------
# Consultas a NOMADS
# ----------------------------------------------------------------------------
def leads_en_listado(html: str, ciclo: str, resolucion: str) -> set[int]:
    """Extrae los fNNN publicados de la página de listado de un ciclo.

    El filtro de NOMADS trabaja sobre el .idx, que se escribe cuando el GRIB
    ya está completo: si hay .idx se cuentan solo esos leads, lo que evita
    pedir un archivo que aún se está generando. Si el listado no muestra ningún
    .idx, se usan todos los GRIB listados (comportamiento de la versión anterior).
    """
    patron = re.compile(rf"gfs\.t{ciclo}z\.pgrb2\.{re.escape(resolucion)}\.f(\d{{3}})(\.idx)?")
    todos: set[int] = set()
    con_idx: set[int] = set()
    for lead, idx in patron.findall(html):
        todos.add(int(lead))
        if idx:
            con_idx.add(int(lead))
    return con_idx or todos


def consultar_archivos_ciclo(
    sesion: requests.Session, cfg: Config, fecha: str, ciclo: str
) -> set[int] | None:
    """Lista los fNNN publicados para ese ciclo; None indica error HTTP/red."""
    try:
        respuesta = sesion.get(url_directorio_ciclo(cfg, fecha, ciclo), timeout=(5, 15))
        respuesta.raise_for_status()
    except requests.RequestException:
        return None
    return leads_en_listado(respuesta.text, ciclo, cfg.modelo.resolucion)


def buscar_ultimo_ciclo_web(
    sesion: requests.Session, cfg: Config, ahora: datetime | None = None
) -> tuple[str, str, set[int]] | None:
    """Busca el ciclo NOMADS más reciente que ya cumplió el retraso en UTC."""
    ahora = (ahora or datetime.now(timezone.utc)).astimezone(timezone.utc)
    limite = ahora - timedelta(hours=cfg.ciclos.retraso_publicacion_horas)
    try:
        respuesta = sesion.get(f"{cfg.modelo.url_prod}/", timeout=(5, 15))
        respuesta.raise_for_status()
    except requests.RequestException:
        return None
    fechas = sorted(set(_RE_FECHAS.findall(respuesta.text)), reverse=True)
    # Los últimos cuatro días cubren un índice que se actualice parcialmente.
    for fecha in fechas[:4]:
        for ciclo in CICLOS:
            nominal = datetime.strptime(fecha + ciclo, "%Y%m%d%H").replace(tzinfo=timezone.utc)
            if nominal > limite:
                continue
            publicados = consultar_archivos_ciclo(sesion, cfg, fecha, ciclo)
            if not publicados:
                continue
            if cfg.ciclos.exigir_completo:
                faltan = sorted(set(horas_pronostico(cfg.modelo, ciclo)) - publicados)
                if faltan:
                    log.info(f"Ciclo {fecha} {ciclo}Z incompleto (faltan {len(faltan)} fNNN, "
                          f"desde f{faltan[0]:03d}); se prueba el anterior.")
                    continue
            return fecha, ciclo, publicados
    return None


def ciclo_estimado(retraso_horas: float, ahora: datetime | None = None) -> tuple[str, str]:
    """Último ciclo nominal cuya espera de retraso ya transcurrió en UTC."""
    ahora = (ahora or datetime.now(timezone.utc)).astimezone(timezone.utc)
    disponible = ahora - timedelta(hours=retraso_horas)
    hora = (disponible.hour // 6) * 6
    return disponible.strftime("%Y%m%d"), f"{hora:02d}"


# ----------------------------------------------------------------------------
# Elección del ciclo
# ----------------------------------------------------------------------------
def _nominal(fecha: str, ciclo: str) -> datetime:
    return datetime.strptime(fecha + ciclo, "%Y%m%d%H").replace(tzinfo=timezone.utc)


def _validar_manual(
    sesion: requests.Session, cfg: Config, fecha: str, ciclo: str
) -> set[int]:
    """Valida un ciclo pedido a mano; lanza ValueError/RuntimeError si no sirve."""
    if not re.fullmatch(r"\d{8}", fecha) or ciclo not in CICLOS:
        raise ValueError("Fecha/ciclo inválidos: usa AAAAMMDD y 00, 06, 12 o 18.")
    try:
        nominal = _nominal(fecha, ciclo)
    except ValueError as exc:
        raise ValueError("La fecha manual no es válida; usa AAAAMMDD.") from exc
    disponible = nominal + timedelta(hours=cfg.ciclos.retraso_publicacion_horas)
    if disponible > datetime.now(timezone.utc):
        raise ValueError(
            "El ciclo manual aún no ha cumplido el retraso de publicación configurado "
            f"(disponible desde {disponible:%Y-%m-%d %H:%M} UTC)."
        )
    publicados = consultar_archivos_ciclo(sesion, cfg, fecha, ciclo)
    if publicados is None:
        raise RuntimeError("No se pudo consultar NOMADS para validar el ciclo solicitado.")
    if not publicados:
        raise RuntimeError(f"NOMADS no publica archivos para {fecha} {ciclo}Z.")
    return publicados


def _pedir_interactivo(
    sesion: requests.Session,
    cfg: Config,
    fecha: str,
    ciclo: str,
    publicados: set[int] | None,
) -> tuple[str, str, set[int] | None]:
    print("Enter = aceptar. Para elegir otro ciclo, escribe exactamente AAAAMMDD HH "
          "(HH: 00, 06, 12 o 18).")
    retraso = cfg.ciclos.retraso_publicacion_horas
    while True:
        entrada = input(f"Fecha y ciclo [{fecha} {ciclo}]: ").strip()
        if not entrada:
            return fecha, ciclo, publicados
        coincidencia = _RE_FECHA_CICLO.fullmatch(entrada)
        if not coincidencia:
            print("Formato inválido. Ejemplo: 20261024 00")
            continue
        fecha_nueva, ciclo_nuevo = coincidencia.groups()
        try:
            nominal = _nominal(fecha_nueva, ciclo_nuevo)
        except ValueError:
            print("La fecha no es válida; usa AAAAMMDD.")
            continue
        disponible = nominal + timedelta(hours=retraso)
        if datetime.now(timezone.utc) < disponible:
            print(f"Ese ciclo aún no cumple el retraso: estará habilitado desde "
                  f"{disponible:%Y-%m-%d %H:%M} UTC.")
            continue
        nuevos = consultar_archivos_ciclo(sesion, cfg, fecha_nueva, ciclo_nuevo)
        if nuevos is None:
            print("No pude comprobar esa carpeta en NOMADS; inténtalo nuevamente.")
            continue
        if not nuevos:
            print("Ese ciclo no tiene archivos publicados en NOMADS; ingresa otro.")
            continue
        print(f"Último fNNN disponible: f{max(nuevos):03d}")
        return fecha_nueva, ciclo_nuevo, nuevos


def elegir_ciclo(
    sesion: requests.Session,
    cfg: Config,
    fecha_solicitada: str | None = None,
    ciclo_solicitado: str | None = None,
    interactivo: bool = True,
) -> tuple[str, str, set[int] | None]:
    """Devuelve (fecha, ciclo, fNNN publicados o None si NOMADS no respondió)."""
    if bool(fecha_solicitada) != bool(ciclo_solicitado):
        raise ValueError("Para elegir un ciclo manualmente debes indicar fecha y ciclo.")
    if fecha_solicitada and ciclo_solicitado:
        return fecha_solicitada, ciclo_solicitado, _validar_manual(
            sesion, cfg, fecha_solicitada, ciclo_solicitado
        )

    retraso = cfg.ciclos.retraso_publicacion_horas
    ahora = datetime.now(timezone.utc)
    ultimo = buscar_ultimo_ciclo_web(sesion, cfg, ahora)
    if ultimo:
        fecha, ciclo, publicados = ultimo
        log.info(f"Última carpeta/ciclo publicado en NOMADS: {fecha} {ciclo}Z")
        log.info(f"Último fNNN listado en esa carpeta: f{max(publicados):03d}")
    else:
        fecha, ciclo = ciclo_estimado(retraso, ahora)
        publicados = None
        log.info("No pude consultar NOMADS; propongo el ciclo según el retraso configurado.")
    log.info(f"Disponibilidad: {retraso:g} h después de la hora nominal del ciclo, calculada en UTC.")
    log.info(f"Recomendación: {fecha} {ciclo}Z")
    if not interactivo:
        log.info("Modo no interactivo: se selecciona automáticamente el ciclo recomendado.")
        return fecha, ciclo, publicados
    return _pedir_interactivo(sesion, cfg, fecha, ciclo, publicados)
