"""Panel Streamlit para iniciar descargas GFS y evitar repetir ciclos creados.

Uso desde la raíz del proyecto:
    pip install -r _0_Visor/requirements.txt
    python Y0Qa1_Visor.py          (o: streamlit run _0_Visor/Y0Qa1_Panel.py)

Secrets/variables: GITHUB_TOKEN, GITHUB_REPO y opcionales GITHUB_WORKFLOW,
GITHUB_REF, GITHUB_CONTROL_PATH. Las cuentas viven en el repo privado indicado
por AUTH_GITHUB_REPO y se leen usando AUTH_GITHUB_TOKEN.
Opcionales: SESION_MAX_INACTIVIDAD_MIN (def. 120) y MOSTRAR_DETALLES_ERROR (def. false).
"""
from __future__ import annotations

import base64
import html
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import streamlit as st

# El visor se ejecuta desde _0_Visor; la raíz del proyecto aporta el paquete compartido _Comun.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _Comun.control_ciclos import ErrorControl, es_afirmativo, leer_filas  # noqa: E402
from accounts import (  # noqa: E402
    ErrorCuentas, ORDEN_PESTANAS, autenticar, cambiar_clave, cargar_cuentas, cargar_cuentas_cacheado,
)
from errores import mostrar_error  # noqa: E402
from limitador import LimitadorIntentos, texto_espera  # noqa: E402

st.set_page_config(page_title="Y0Qa1 · Descargas GFS", page_icon="🌀", layout="wide")
st.markdown(
    """
    <style>
      .stApp { background-color: #111827; color: #F9FAFB; }
      [data-testid="stMainBlockContainer"] { color: #F9FAFB; }
      [data-testid="stMetric"] { background-color: #1F2937; border-radius: 0.5rem; padding: 0.75rem; }
      [data-testid="stHeader"] { display: none; }
      [data-testid="stMainBlockContainer"] { padding-top: 0.35rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

API = "https://api.github.com"
CICLOS = ("00", "06", "12", "18")
SEGUNDOS_ENTRE_CONSULTAS = 5
MAX_BUSQUEDAS_RUN = 15            # ~75 s esperando que aparezca la ejecución
MAX_SEGUIMIENTO_S = 60 * 60       # deja de seguir una ejecución tras 60 min


def conf(clave, defecto=None):
    try:
        valor = st.secrets[clave]
    except Exception:
        valor = None
    if valor in (None, ""):
        valor = os.environ.get(clave)
    return valor if valor not in (None, "") else defecto


TOKEN = conf("GITHUB_TOKEN")
REPO = conf("GITHUB_REPO")
WORKFLOW = conf("GITHUB_WORKFLOW", "Get_fnnn.yml")
CONTROL_PATH = conf("GITHUB_CONTROL_PATH", "___Data/control.xlsx")
DEMO = not TOKEN or not REPO
INTRO_IMAGE = Path(__file__).with_name("_Intro.png")
try:
    INACTIVIDAD_MAX_S = max(5, int(conf("SESION_MAX_INACTIVIDAD_MIN", 120))) * 60
except (TypeError, ValueError):
    INACTIVIDAD_MAX_S = 120 * 60


@st.cache_resource
def limitador_login() -> LimitadorIntentos:
    """Un único limitador compartido por todas las sesiones del servidor."""
    return LimitadorIntentos(max_fallos=5, base_s=30, tope_s=900, olvido_s=1800)


# --------------------------------------------------------------------------- GitHub
def gh(metodo, ruta, **kw):
    try:
        return requests.request(
            metodo, API + ruta, timeout=20,
            headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28"}, **kw,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"No se pudo conectar con GitHub: {exc}") from exc


def explica(respuesta):
    base = {
        401: "El token de GitHub no es válido o venció.",
        403: "El token necesita Actions: lectura/escritura y Contents: lectura para consultar control.xlsx.",
        404: "No se encontró el repositorio o workflow. Revisa GITHUB_REPO y GITHUB_WORKFLOW.",
        422: "GitHub rechazó el workflow o los datos enviados.",
    }.get(respuesta.status_code, f"GitHub respondió con error {respuesta.status_code}.")
    try:
        detalle = respuesta.json().get("message", "")
    except Exception:
        detalle = ""
    return f"{base} {('(' + detalle + ')') if detalle else ''}".strip()


@st.cache_data(ttl=3600, show_spinner=False)
def rama():
    """Rama por defecto del repositorio (cambia casi nunca: se consulta una vez por hora)."""
    ref = conf("GITHUB_REF")
    if ref:
        return ref
    respuesta = gh("GET", f"/repos/{REPO}")
    if respuesta.status_code != 200:
        raise RuntimeError(explica(respuesta))
    return respuesta.json()["default_branch"]


@st.cache_data(ttl=60, show_spinner=False)
def filas_control():
    """Control de ciclos como filas matriciales (caché de 60 s; se invalida al terminar una ejecución)."""
    try:
        if DEMO:
            ruta_local = Path(__file__).resolve().parent.parent / "___Data" / "control.xlsx"
            return leer_filas(ruta_local) if ruta_local.is_file() else []
        respuesta = gh("GET", f"/repos/{REPO}/contents/{CONTROL_PATH}", params={"ref": rama()})
        if respuesta.status_code == 404:
            return []
        if respuesta.status_code != 200:
            raise RuntimeError(explica(respuesta))
        return leer_filas(base64.b64decode(respuesta.json().get("content", "")))
    except RuntimeError:
        raise
    except ErrorControl as exc:
        raise RuntimeError(f"No se pudo leer {CONTROL_PATH}: {exc}") from exc


def ciclo_descargado(fecha, ciclo):
    """Consulta control.xlsx en el repositorio de GitHub (lectura fresca)."""
    filas_control.clear()
    for fila in filas_control():
        if fila["fecha_key"] == fecha:
            return es_afirmativo(fila.get(ciclo, ""))
    return False


def dispara(inputs):
    respuesta = gh("POST", f"/repos/{REPO}/actions/workflows/{WORKFLOW}/dispatches",
                   json={"ref": rama(), "inputs": inputs})
    if respuesta.status_code != 204:
        raise RuntimeError(explica(respuesta))


def lista_runs(n=8):
    respuesta = gh("GET", f"/repos/{REPO}/actions/workflows/{WORKFLOW}/runs", params={"per_page": n})
    if respuesta.status_code != 200:
        raise RuntimeError(explica(respuesta))
    return respuesta.json().get("workflow_runs", [])


@st.cache_data(ttl=20, show_spinner=False)
def lista_runs_cacheada(n=8):
    """Historial para mostrar (caché corta). El seguimiento de una ejecución usa lista_runs() directo."""
    return lista_runs(n)


def obtiene_run(run_id):
    respuesta = gh("GET", f"/repos/{REPO}/actions/runs/{run_id}")
    if respuesta.status_code != 200:
        raise RuntimeError(explica(respuesta))
    return respuesta.json()


def ciclo_reciente(ahora=None):
    """Selecciona el ciclo GFS más reciente que ya debería estar publicado (UTC)."""
    ahora = ahora or datetime.now(timezone.utc)
    hora = ahora.hour + ahora.minute / 60
    if hora <= 4.3:
        return (ahora - timedelta(days=1)).date(), "18"
    return ahora.date(), "00" if hora <= 10.3 else "06" if hora <= 16.3 else "12" if hora <= 22.3 else "18"


def etiqueta(run):
    if run["status"] != "completed":
        return "En curso" if run["status"] == "in_progress" else "En cola"
    return {"success": "Terminada", "failure": "Falló", "cancelled": "Cancelada",
            "skipped": "Omitida", "timed_out": "Tiempo agotado"}.get(run.get("conclusion"), "Terminada")


def _fecha_iso(texto):
    return datetime.fromisoformat(texto.replace("Z", "+00:00"))


def minutos(run):
    inicio = _fecha_iso(run.get("run_started_at") or run["created_at"])
    return f"{int((datetime.now(timezone.utc) - inicio).total_seconds() // 60)} min"


# --------------------------------------------------------------------------- sesión
def _cerrar_sesion(mensaje: str | None = None):
    for clave in ("usuario", "ultimo_acceso", "seguimiento"):
        st.session_state.pop(clave, None)
    if mensaje:
        st.session_state["aviso_sesion"] = mensaje


def _pantalla_acceso():
    st.image(str(INTRO_IMAGE), use_container_width=True)
    st.subheader("Bienvenido al visor Y0Qa1")
    st.caption("Ingresa tu usuario y clave para abrir las pestañas que tienes autorizadas.")
    aviso = st.session_state.pop("aviso_sesion", None)
    if aviso:
        st.warning(aviso)
    with st.form("acceso_visor", clear_on_submit=True):
        usuario_ingresado = st.text_input("Usuario")
        intento = st.text_input("Clave", type="password")
        ingresar = st.form_submit_button("Ingresar", type="primary")
    if not ingresar:
        return
    limitador = limitador_login()
    clave_usuario = f"u:{usuario_ingresado}"
    espera = limitador.segundos_restantes(clave_usuario)
    if espera:
        st.error(f"Demasiados intentos fallidos. Espera {texto_espera(espera)} antes de volver a intentar.")
        return
    try:
        cuenta = autenticar(cargar_cuentas(), usuario_ingresado, intento)
    except ErrorCuentas as exc:
        mostrar_error("No se pudo verificar el acceso en este momento. Intenta de nuevo en unos minutos.", exc)
        return
    if cuenta:
        limitador.registrar_exito(clave_usuario)
        st.session_state["usuario"] = cuenta["username"]
        st.session_state["ultimo_acceso"] = time.time()
        st.rerun()
    bloqueo = limitador.registrar_fallo(clave_usuario)
    if bloqueo:
        st.error(f"Demasiados intentos fallidos. Espera {texto_espera(bloqueo)} antes de volver a intentar.")
    else:
        st.error("Usuario o clave incorrectos.")


if st.session_state.get("usuario"):
    ultimo = st.session_state.get("ultimo_acceso")
    if ultimo is not None and time.time() - ultimo > INACTIVIDAD_MAX_S:
        _cerrar_sesion("Tu sesión se cerró por inactividad. Ingresa nuevamente.")
    else:
        st.session_state["ultimo_acceso"] = time.time()

if not st.session_state.get("usuario"):
    _pantalla_acceso()
    st.stop()

def _buscar_cuenta(cuentas: dict, nombre: str):
    return next((u for u in cuentas["users"] if u["username"].upper() == nombre.upper()), None)


try:
    cuenta_actual = _buscar_cuenta(cargar_cuentas_cacheado(), st.session_state["usuario"])
    if cuenta_actual is None:
        # Puede ser una cuenta creada hace menos de 60 s (la caché aún no la tiene): lectura fresca.
        cargar_cuentas_cacheado.clear()
        cuenta_actual = _buscar_cuenta(cargar_cuentas_cacheado(), st.session_state["usuario"])
    if cuenta_actual is None:
        raise KeyError("La cuenta ya no existe.")
except (ErrorCuentas, KeyError) as exc:
    _cerrar_sesion()
    mostrar_error("No se pudo cargar la cuenta. Inicia sesión nuevamente.", exc)
    st.stop()

if cuenta_actual.get("must_change_password", True):
    st.image(str(INTRO_IMAGE), use_container_width=True)
    st.subheader("Cambia tu clave provisoria")
    st.caption("Define una clave nueva de al menos 8 caracteres antes de continuar.")
    with st.form("cambiar_clave", clear_on_submit=True):
        nueva_clave = st.text_input("Nueva clave", type="password")
        confirmar_clave = st.text_input("Repite la nueva clave", type="password")
        guardar_clave = st.form_submit_button("Guardar clave", type="primary")
    if guardar_clave:
        if len(nueva_clave) < 8:
            st.error("La nueva clave debe tener al menos 8 caracteres.")
        elif nueva_clave != confirmar_clave:
            st.error("Las claves no coinciden.")
        else:
            try:
                cambiar_clave(cuenta_actual["username"], nueva_clave)
                st.success("Clave actualizada. Ya puedes acceder al visor.")
                st.rerun()
            except (ErrorCuentas, OSError) as exc:
                mostrar_error("No se pudo guardar la clave. Intenta de nuevo en unos minutos.", exc)
    st.stop()


# --------------------------------------------------------------------------- seguimiento de una ejecución
def _iniciar_seguimiento(t0: datetime, fecha_key: str, ciclo: str):
    st.session_state["seguimiento"] = {
        "t0": t0.isoformat(), "fecha": fecha_key, "ciclo": ciclo, "run_id": None, "busquedas": 0,
        "inicio": time.time(), "terminado": False, "estado": "running", "mensaje": "", "url": None,
    }


def _terminar_seguimiento(seg: dict, estado: str, mensaje: str, url: str | None = None):
    seg.update(terminado=True, estado=estado, mensaje=mensaje, url=url)
    filas_control.clear()
    st.rerun()     # rerun completo: detiene el refresco periódico y actualiza el control de ciclos


def _actualizar_seguimiento():
    """Una consulta de estado. Se ejecuta cada pocos segundos mientras la ejecución sigue en curso."""
    seg = st.session_state.get("seguimiento")
    if not seg or seg["terminado"]:
        return
    try:
        if seg["run_id"] is None:
            t0 = datetime.fromisoformat(seg["t0"])
            candidatos = [r for r in lista_runs()
                          if r["event"] == "workflow_dispatch" and _fecha_iso(r["created_at"]) >= t0]
            if candidatos:
                seg["run_id"] = candidatos[0]["id"]
            else:
                seg["busquedas"] += 1
                if seg["busquedas"] >= MAX_BUSQUEDAS_RUN:
                    _terminar_seguimiento(
                        seg, "error", "La ejecución aún no aparece; actualiza el historial en un momento.")
                st.info("Solicitud enviada. Buscando la ejecución…")
                return
        run = obtiene_run(seg["run_id"])
    except RuntimeError as exc:
        mostrar_error("No se pudo consultar el estado de la ejecución en GitHub.", exc)
        _terminar_seguimiento(seg, "error", "No se pudo consultar el estado de la ejecución en GitHub.")
    if run["status"] == "completed":
        if run.get("conclusion") == "success":
            _terminar_seguimiento(seg, "ok", f"Ejecución #{run['run_number']} terminada · {minutos(run)}",
                                  run["html_url"])
        _terminar_seguimiento(seg, "error", f"Ejecución #{run['run_number']}: {etiqueta(run)}", run["html_url"])
    if time.time() - seg["inicio"] > MAX_SEGUIMIENTO_S:
        _terminar_seguimiento(seg, "error", f"Ejecución #{run['run_number']} sigue en curso.", run["html_url"])
    st.info(f"Ejecución #{run['run_number']}: {etiqueta(run)} · {minutos(run)}")
    st.link_button("Ver registro en GitHub", run["html_url"])


def _montar_seguimiento():
    seg = st.session_state.get("seguimiento")
    if not seg:
        return
    if not seg["terminado"]:
        # Refresco periódico solo de este bloque (no recarga toda la página ni bloquea la sesión).
        st.fragment(run_every=SEGUNDOS_ENTRE_CONSULTAS)(_actualizar_seguimiento)()
        return
    if seg["estado"] == "ok":
        st.success(seg["mensaje"])
    else:
        st.error(seg["mensaje"])
        if seg.get("run_id"):
            st.write("Revisa el registro de GitHub para conocer el error o si el ciclo estaba incompleto.")
    if seg.get("url"):
        st.link_button("Ver registro en GitHub", seg["url"])


def mostrar_descarga():
    st.title("Y0Qa1 · Panel de descargas GFS")
    st.caption("El ciclo se descarga y convierte a NetCDF en GitHub Actions.")

    if DEMO:
        st.info("Vista previa local: puedes revisar el panel; las descargas están desactivadas hasta configurar GitHub.")

    modo = st.radio("Ciclo", ["Automático (el más reciente)", "Elegir"], horizontal=True)
    fecha_reciente, ciclo_reciente_utc = ciclo_reciente()
    if modo == "Elegir":
        col_fecha, col_ciclo = st.columns(2)
        fecha = col_fecha.date_input("Fecha", value=fecha_reciente)
        ciclo = col_ciclo.selectbox("Ciclo (UTC)", CICLOS, index=CICLOS.index(ciclo_reciente_utc))
    else:
        fecha, ciclo = fecha_reciente, ciclo_reciente_utc
        st.caption(f"Ciclo seleccionado: {fecha:%Y%m%d} {ciclo}Z (UTC).")
    forzar = st.checkbox("Forzar aunque control.xlsx indique que ya existe")

    if st.button("Iniciar descarga", type="primary"):
        fecha_key = fecha.strftime("%Y%m%d")
        try:
            if DEMO:
                st.info("Vista previa: no se envió ninguna solicitud ni se inició una descarga.")
            elif not forzar and ciclo_descargado(fecha_key, ciclo):
                st.info(f"El ciclo {fecha_key} {ciclo}Z ya existe. Se omite la descarga.")
            else:
                inputs = {"fecha": fecha_key, "ciclo": ciclo}
                if forzar:
                    inputs["forzar"] = "true"
                t0 = datetime.now(timezone.utc) - timedelta(seconds=15)
                dispara(inputs)
                _iniciar_seguimiento(t0, fecha_key, ciclo)
        except RuntimeError as exc:
            mostrar_error("No se pudo comunicar con GitHub. Intenta de nuevo en un momento.", exc)

    _montar_seguimiento()

    st.divider()
    st.subheader("Últimas ejecuciones")
    if DEMO:
        st.caption("El historial de GitHub aparecerá al configurar GITHUB_TOKEN y GITHUB_REPO.")
    else:
        if st.button("Actualizar historial"):
            lista_runs_cacheada.clear()
            filas_control.clear()
            st.rerun()
        try:
            runs = lista_runs_cacheada()
            filas = [{"N°": run["run_number"],
                      "Ciclo": run.get("display_title", ""),
                      "Estado": etiqueta(run),
                      "Inicio (UTC)": _fecha_iso(run["created_at"]).strftime("%d-%m %H:%M"),
                      "Ver": run["html_url"]} for run in runs]
            if filas:
                st.dataframe(filas, hide_index=True,
                             column_config={"Ver": st.column_config.LinkColumn("Ver", display_text="Abrir")})
            else:
                st.caption("Todavía no hay ejecuciones.")
        except RuntimeError as exc:
            mostrar_error("No se pudo leer el historial de ejecuciones.", exc)

    st.divider()
    st.subheader("Control de ciclos · últimos 3 días")
    try:
        control = filas_control()[:3]
        if control:
            st.dataframe([{k: fila.get(k, "") for k in ("fecha", "00", "06", "12", "18")}
                          for fila in control], hide_index=True, use_container_width=True,
                         column_config={c: st.column_config.TextColumn(c) for c in ("00", "06", "12", "18")})
        else:
            st.caption("Todavía no hay ciclos registrados en control.xlsx.")
    except RuntimeError as exc:
        mostrar_error("No se pudo leer el control de ciclos.", exc, aviso=True)


# --------------------------------------------------------------------------- pestañas
nombres_visibles = [nombre for nombre in ORDEN_PESTANAS if nombre in cuenta_actual.get("tabs", [])]
col_menu, col_usuario, col_cerrar = st.columns([5, 1.7, 1.3], vertical_alignment="bottom")
with col_menu:
    pestana_actual = st.selectbox("Pestaña", nombres_visibles, label_visibility="collapsed")
with col_usuario:
    st.markdown(
        f"<div style='height:2.6rem;display:flex;align-items:center;justify-content:flex-end'>"
        f"Usuario: <strong style='margin-left:.35rem'>{html.escape(str(cuenta_actual['username']))}</strong></div>",
        unsafe_allow_html=True,
    )
with col_cerrar:
    if st.button("Cerrar sesión", use_container_width=True):
        _cerrar_sesion()
        st.rerun()

if pestana_actual == "Descarga":
    mostrar_descarga()
elif pestana_actual == "Tablas":
    try:
        from tablas import mostrar_tablas
        mostrar_tablas()
    except Exception as exc:
        mostrar_error("No se pudo cargar la pestaña Tablas.", exc)
else:
    st.title(f"Y0Qa1 · {pestana_actual}")
    st.info(f"La pestaña {pestana_actual} está preparada; su contenido se añadirá después.")
