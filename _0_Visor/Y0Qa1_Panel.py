"""Panel Streamlit para iniciar descargas GFS y evitar repetir ciclos creados.

Uso desde la raíz del proyecto: pip install -r _0_Visor/requirements_panel.txt;
python Y0Qa1_Panel.py
Secrets/variables: GITHUB_TOKEN, GITHUB_REPO y opcionales GITHUB_WORKFLOW,
GITHUB_REF, GITHUB_CONTROL_PATH. Las cuentas viven en el repo privado indicado
por AUTH_GITHUB_REPO y se leen usando AUTH_GITHUB_TOKEN.
"""
from __future__ import annotations

import base64
import io
import os
import time
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import streamlit as st
from openpyxl import load_workbook
from accounts import ErrorCuentas, ORDEN_PESTANAS, autenticar, cambiar_clave, cargar_cuentas

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


def rama():
    ref = conf("GITHUB_REF")
    if ref:
        return ref
    respuesta = gh("GET", f"/repos/{REPO}")
    if respuesta.status_code != 200:
        raise RuntimeError(explica(respuesta))
    return respuesta.json()["default_branch"]


MESES_ES = ("enero", "febrero", "marzo", "abril", "mayo", "junio",
            "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")


def fecha_control(valor):
    texto = str(valor or "").strip()
    if re.fullmatch(r"\d{8}", texto):
        return texto
    m = re.fullmatch(r"(\d{1,2})\.([a-záéíóú]+)\.(\d{4})", texto, re.I)
    if not m:
        return ""
    try:
        mes = MESES_ES.index(m.group(2).casefold()) + 1
        return datetime(int(m.group(3)), mes, int(m.group(1))).strftime("%Y%m%d")
    except ValueError:
        return ""


def filas_control():
    """Devuelve el control como filas matriciales, conservando lectura del formato anterior."""
    try:
        if DEMO:
            ruta_local = Path(__file__).resolve().parent.parent / "___Data" / "control.xlsx"
            if not ruta_local.is_file():
                return []
            contenido = ruta_local.read_bytes()
        else:
            respuesta = gh("GET", f"/repos/{REPO}/contents/{CONTROL_PATH}", params={"ref": rama()})
            if respuesta.status_code == 404:
                return []
            if respuesta.status_code != 200:
                raise RuntimeError(explica(respuesta))
            contenido = base64.b64decode(respuesta.json().get("content", ""))
        libro = load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
        try:
            filas = list(libro.active.iter_rows(values_only=True))
        finally:
            libro.close()
        if not filas:
            return []
        encabezados = [str(v or "").strip().casefold() for v in filas[0]]
        ciclos = ("00", "06", "12", "18")
        if all(c in encabezados for c in ciclos):
            salida = []
            for fila in filas[1:]:
                fecha = fecha_control(fila[0] if fila else "")
                if not fecha:
                    continue
                salida.append({"fecha_key": fecha, "fecha": str(fila[0]), **{
                    c: str(fila[encabezados.index(c)] or "").strip() if encabezados.index(c) < len(fila) else ""
                    for c in ciclos
                }})
            return sorted(salida, key=lambda f: f["fecha_key"], reverse=True)
        # Compatibilidad con control antiguo: fecha | ciclo | existe o no.
        salida = {}
        for fila in filas[1:]:
            if len(fila) < 3:
                continue
            fecha, ciclo = fecha_control(fila[0]), str(fila[1] or "").zfill(2)
            if fecha and ciclo in ciclos:
                registro = salida.setdefault(fecha, {"fecha_key": fecha, "fecha": fecha})
                registro[ciclo] = str(fila[2] or "")
        return sorted(salida.values(), key=lambda f: f["fecha_key"], reverse=True)
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"No se pudo leer {CONTROL_PATH}: {exc}") from exc


def ciclo_descargado(fecha, ciclo):
    """Consulta control.xlsx en el repositorio de GitHub."""
    for fila in filas_control():
        if fila["fecha_key"] == fecha:
            return str(fila.get(ciclo, "")).strip().casefold() in {"sí", "si", "true", "yes", "1"}
    return False


def dispara(inputs):
    respuesta = gh("POST", f"/repos/{REPO}/actions/workflows/{WORKFLOW}/dispatches",
                    json={"ref": rama(), "inputs": inputs})
    if respuesta.status_code != 204:
        raise RuntimeError(explica(respuesta))


def lista_runs(n=8):
    respuesta = gh("GET", f"/repos/{REPO}/actions/workflows/{WORKFLOW}/runs",
                    params={"per_page": n})
    if respuesta.status_code != 200:
        raise RuntimeError(explica(respuesta))
    return respuesta.json().get("workflow_runs", [])


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


def minutos(run):
    inicio = datetime.fromisoformat((run.get("run_started_at") or run["created_at"]).replace("Z", "+00:00"))
    return f"{int((datetime.now(timezone.utc) - inicio).total_seconds() // 60)} min"


if not st.session_state.get("usuario"):
    st.image(str(INTRO_IMAGE), use_container_width=True)
    st.subheader("Bienvenido al visor Y0Qa1")
    st.caption("Ingresa tu usuario y clave para abrir las pestañas que tienes autorizadas.")
    with st.form("acceso_visor", clear_on_submit=True):
        usuario_ingresado = st.text_input("Usuario")
        intento = st.text_input("Clave", type="password")
        ingresar = st.form_submit_button("Ingresar", type="primary")
    if ingresar:
        try:
            cuenta = autenticar(cargar_cuentas(), usuario_ingresado, intento)
            if cuenta:
                st.session_state["usuario"] = cuenta["username"]
                st.rerun()
            st.error("Usuario o clave incorrectos.")
        except ErrorCuentas as exc:
            st.error(str(exc))
    st.stop()

try:
    cuenta_actual = next(
        u for u in cargar_cuentas()["users"]
        if u["username"].upper() == st.session_state["usuario"].upper()
    )
except (ErrorCuentas, StopIteration, KeyError) as exc:
    st.session_state.pop("usuario", None)
    st.error(f"No se pudo cargar la cuenta. Inicia sesión nuevamente. {exc}")
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
                st.error(str(exc))
    st.stop()

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
                with st.status("Solicitud enviada. Buscando la ejecución…", expanded=True) as estado:
                    run = None
                    for _ in range(15):
                        time.sleep(4)
                        candidatos = [r for r in lista_runs()
                                      if r["event"] == "workflow_dispatch"
                                      and datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")) >= t0]
                        if candidatos:
                            run = candidatos[0]
                            break
                    if not run:
                        estado.update(label="La ejecución aún no aparece; actualiza el historial en un momento.",
                                      state="error")
                    else:
                        inicio = time.monotonic()
                        while run["status"] != "completed" and time.monotonic() - inicio < 60 * 60:
                            estado.update(label=f"Ejecución #{run['run_number']}: {etiqueta(run)} · {minutos(run)}",
                                          state="running")
                            time.sleep(6)
                            run = obtiene_run(run["id"])
                        if run["status"] == "completed" and run.get("conclusion") == "success":
                            estado.update(label=f"Ejecución #{run['run_number']} terminada · {minutos(run)}",
                                          state="complete")
                        elif run["status"] != "completed":
                            estado.update(label=f"Ejecución #{run['run_number']} sigue en curso.", state="error")
                        else:
                            estado.update(label=f"Ejecución #{run['run_number']}: {etiqueta(run)}", state="error")
                            st.write("Revisa el registro de GitHub para conocer el error o si el ciclo estaba incompleto.")
                        st.link_button("Ver registro en GitHub", run["html_url"])
        except RuntimeError as exc:
            st.error(str(exc))
    
    st.divider()
    st.subheader("Últimas ejecuciones")
    if DEMO:
        st.caption("El historial de GitHub aparecerá al configurar GITHUB_TOKEN y GITHUB_REPO.")
    else:
        if st.button("Actualizar historial"):
            st.rerun()
        try:
            runs = lista_runs()
            filas = [{"N°": run["run_number"],
                      "Ciclo": run.get("display_title", ""),
                      "Estado": etiqueta(run),
                      "Inicio (UTC)": datetime.fromisoformat(run["created_at"].replace("Z", "+00:00")).strftime("%d-%m %H:%M"),
                      "Ver": run["html_url"]} for run in runs]
            if filas:
                st.dataframe(filas, hide_index=True,
                             column_config={"Ver": st.column_config.LinkColumn("Ver", display_text="Abrir")})
            else:
                st.caption("Todavía no hay ejecuciones.")
        except RuntimeError as exc:
            st.error(str(exc))

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
        st.warning(str(exc))

nombres_visibles = [nombre for nombre in ORDEN_PESTANAS if nombre in cuenta_actual.get("tabs", [])]
col_menu, col_usuario, col_cerrar = st.columns([5, 1.7, 1.3], vertical_alignment="bottom")
with col_menu:
    pestana_actual = st.selectbox("Pestaña", nombres_visibles, label_visibility="collapsed")
with col_usuario:
    st.markdown(
        f"<div style='height:2.6rem;display:flex;align-items:center;justify-content:flex-end'>"
        f"Usuario: <strong style='margin-left:.35rem'>{cuenta_actual['username']}</strong></div>",
        unsafe_allow_html=True,
    )
with col_cerrar:
    if st.button("Cerrar sesión", use_container_width=True):
        st.session_state.pop("usuario", None)
        st.rerun()

st.divider()
if pestana_actual == "Descarga":
    mostrar_descarga()
elif pestana_actual == "Tablas":
    try:
        from tablas import mostrar_tablas
        mostrar_tablas()
    except Exception as exc:
        st.error(f"No se pudo cargar la pestaña Tablas: {exc}")
else:
    st.title(f"Y0Qa1 · {pestana_actual}")
    st.info(f"La pestaña {pestana_actual} está preparada; su contenido se añadirá después.")
