"""Gestión local de cuentas, claves y permisos de pestañas del visor."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
from pathlib import Path

CONFIG_CUENTAS = Path(__file__).with_name("accounts.json")
ORDEN_PESTANAS = ("Tablas", "UV", "Corte temporal", "Plan", "Descarga")


class ErrorCuentas(ValueError):
    """El archivo de cuentas o una cuenta no es válido."""


def cargar_cuentas(ruta: Path = CONFIG_CUENTAS) -> dict:
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ErrorCuentas(f"No se pudo leer {ruta}: {exc}") from exc
    if datos.get("version") != 1 or datos.get("kdf") != "pbkdf2_sha256":
        raise ErrorCuentas("Formato o versión de accounts.json no reconocidos.")
    iteraciones = datos.get("iterations")
    if not isinstance(iteraciones, int) or not 100_000 <= iteraciones <= 2_000_000:
        raise ErrorCuentas("El número de iteraciones PBKDF2 está fuera del rango permitido.")
    if not isinstance(datos.get("users"), list):
        raise ErrorCuentas("accounts.json debe incluir una lista 'users'.")
    return datos


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


def _guardar(datos: dict, ruta: Path) -> None:
    temporal = ruta.with_name(ruta.name + ".part")
    temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporal, ruta)


def cambiar_clave(usuario: str, nueva: str, ruta: Path = CONFIG_CUENTAS) -> None:
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


def crear_usuario(usuario: str, clave: str, pestañas: list[str], ruta: Path = CONFIG_CUENTAS) -> None:
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
