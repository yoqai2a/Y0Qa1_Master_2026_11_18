"""Autenticación del visor contra el archivo de cuentas del repo privado."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import base64
from pathlib import Path
from urllib.parse import quote

import requests
import streamlit as st

CONFIG_CUENTAS = Path(__file__).with_name("accounts.json")
ORDEN_PESTANAS = ("Tablas", "UV", "Corte temporal", "Plan", "Descarga")
API_GITHUB = "https://api.github.com"


class ErrorCuentas(ValueError):
    """El archivo de cuentas o una cuenta no es válido."""


def _config(clave: str, defecto: str | None = None) -> str | None:
    try:
        valor = st.secrets.get(clave)
    except Exception:
        valor = None
    if valor in (None, ""):
        valor = os.environ.get(clave)
    return str(valor) if valor not in (None, "") else defecto


def _config_api() -> tuple[str, str, str, dict, dict]:
    repo = _config("AUTH_GITHUB_REPO")
    token = _config("AUTH_GITHUB_TOKEN")
    archivo = _config("AUTH_GITHUB_FILE", "_0_Visor/accounts.json")
    rama = _config("AUTH_GITHUB_BRANCH", "main")
    if not repo or not token or "/" not in repo:
        raise ErrorCuentas(
            "Configura AUTH_GITHUB_REPO y AUTH_GITHUB_TOKEN en los secretos del visor "
            "para conectar el repositorio privado de cuentas."
        )
    url = f"{API_GITHUB}/repos/{repo}/contents/{quote(archivo, safe='/')}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    parametros = {"ref": rama} if rama else {}
    return url, rama, archivo, headers, parametros


def _leer_remoto() -> tuple[dict, str]:
    url, _, archivo, headers, parametros = _config_api()
    try:
        respuesta = requests.get(url, headers=headers, params=parametros, timeout=15)
        if respuesta.status_code != 200:
            if respuesta.status_code in (401, 403, 404):
                raise ErrorCuentas(
                    f"No se pudo leer {archivo} del repositorio privado "
                    f"(GitHub {respuesta.status_code}). Revisa AUTH_GITHUB_REPO (owner/repo), "
                    "AUTH_GITHUB_BRANCH, AUTH_GITHUB_FILE y que el token fine-grained incluya "
                    "este repositorio privado con Contents: read. GitHub también responde 404 "
                    "cuando un token no está autorizado para ver un repo privado."
                )
            raise ErrorCuentas(f"GitHub respondió {respuesta.status_code} al leer las cuentas.")
        contenido = base64.b64decode(respuesta.json().get("content", "")).decode("utf-8")
        return json.loads(contenido), str(respuesta.json().get("sha", ""))
    except (requests.RequestException, ValueError, KeyError) as exc:
        if isinstance(exc, ErrorCuentas):
            raise
        raise ErrorCuentas(f"No se pudo leer la configuración privada de cuentas: {exc}") from exc


def _validar(datos: dict) -> dict:
    if datos.get("version") != 1 or datos.get("kdf") != "pbkdf2_sha256":
        raise ErrorCuentas("Formato o versión de accounts.json no reconocidos.")
    iteraciones = datos.get("iterations")
    if not isinstance(iteraciones, int) or not 100_000 <= iteraciones <= 2_000_000:
        raise ErrorCuentas("El número de iteraciones PBKDF2 está fuera del rango permitido.")
    if not isinstance(datos.get("users"), list):
        raise ErrorCuentas("accounts.json debe incluir una lista 'users'.")
    return datos


def cargar_cuentas(ruta: Path | None = None) -> dict:
    if ruta is None:
        datos, _ = _leer_remoto()
        return _validar(datos)
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ErrorCuentas(f"No se pudo leer {ruta}: {exc}") from exc
    return _validar(datos)


def usuarios_por_nombre(datos: dict) -> dict[str, dict]:
    return {str(u.get("username", "")).upper(): u for u in datos["users"]}


def autenticar(datos: dict, usuario: str, clave: str) -> dict | None:
    cuenta = usuarios_por_nombre(datos).get(usuario.strip().upper())
    if cuenta is None:
        # Mantiene un coste parecido para nombres inexistentes.
        hashlib.pbkdf2_hmac("sha256", clave.encode("utf-8"), b"visor-invalid-user", datos["iterations"])
        return None
    try:
        sal = bytes.fromhex(cuenta["salt"])
        esperado = bytes.fromhex(cuenta["password_hash"])
    except (KeyError, ValueError) as exc:
        raise ErrorCuentas(f"La clave guardada para {cuenta.get('username', '?')} está dañada.") from exc
    obtenido = hashlib.pbkdf2_hmac("sha256", clave.encode("utf-8"), sal, datos["iterations"])
    return cuenta if hmac.compare_digest(obtenido, esperado) else None


def _guardar(datos: dict, ruta: Path | None = None) -> None:
    contenido = json.dumps(datos, ensure_ascii=False, indent=2) + "\n"
    if ruta is not None:
        temporal = ruta.with_name(ruta.name + ".part")
        temporal.write_text(contenido, encoding="utf-8")
        os.replace(temporal, ruta)
        return
    url, rama, archivo, headers, _ = _config_api()
    _, sha = _leer_remoto()
    payload = {
        "message": "Actualizar cuentas del visor",
        "content": base64.b64encode(contenido.encode("utf-8")).decode("ascii"),
        "sha": sha,
        "branch": rama,
    }
    try:
        respuesta = requests.put(url, headers=headers, json=payload, timeout=20)
    except requests.RequestException as exc:
        raise ErrorCuentas(f"No se pudo guardar la cuenta en el repositorio privado: {exc}") from exc
    if respuesta.status_code not in (200, 201):
        raise ErrorCuentas(
            f"GitHub no guardó {archivo} (HTTP {respuesta.status_code}). "
            "El token privado necesita Contents: write."
        )


def cambiar_clave(usuario: str, nueva: str, ruta: Path | None = None) -> None:
    if len(nueva) < 8:
        raise ErrorCuentas("La clave debe tener al menos 8 caracteres.")
    datos = cargar_cuentas(ruta)
    cuenta = usuarios_por_nombre(datos).get(usuario.strip().upper())
    if cuenta is None:
        raise ErrorCuentas("La cuenta no existe.")
    cuenta["salt"] = secrets.token_hex(16)
    cuenta["password_hash"] = hashlib.pbkdf2_hmac(
        "sha256", nueva.encode("utf-8"), bytes.fromhex(cuenta["salt"]), datos["iterations"]
    ).hex()
    cuenta["must_change_password"] = False
    _guardar(datos, ruta)


def crear_usuario(usuario: str, clave: str, pestañas: list[str], ruta: Path | None = None) -> None:
    datos = cargar_cuentas(ruta)
    usuario = usuario.strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{5,20}", usuario):
        raise ErrorCuentas("El usuario debe tener entre 5 y 20 letras A-Z o números.")
    if usuario in usuarios_por_nombre(datos):
        raise ErrorCuentas(f"El usuario {usuario} ya existe.")
    if not clave:
        raise ErrorCuentas("La clave provisoria no puede estar vacía.")
    invalidas = sorted(set(pestañas) - set(ORDEN_PESTANAS))
    if invalidas:
        raise ErrorCuentas(f"Pestañas no reconocidas: {', '.join(invalidas)}")
    permisos = [p for p in ORDEN_PESTANAS if p == "Descarga" or p in pestañas]
    sal = secrets.token_bytes(16)
    cuenta = {
        "username": usuario,
        "salt": sal.hex(),
        "password_hash": hashlib.pbkdf2_hmac("sha256", clave.encode("utf-8"), sal,
                                             datos["iterations"]).hex(),
        "must_change_password": True,
        "tabs": permisos,
    }
    datos["users"].append(cuenta)
    _guardar(datos, ruta)
