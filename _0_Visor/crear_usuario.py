"""Agrega una cuenta al visor sin guardar la clave en texto plano."""
from getpass import getpass

from accounts import ErrorCuentas, ORDEN_PESTANAS, crear_usuario


def main() -> int:
    usuario = input("Usuario nuevo (5-20 caracteres A-Z/0-9): ").strip().upper()
    clave = getpass("Clave provisoria: ")
    repetir = getpass("Repite la clave: ")
    if clave != repetir:
        print("Las claves no coinciden.")
        return 1
    print("Pestañas disponibles: " + ", ".join(ORDEN_PESTANAS))
    entrada = input("Permisos adicionales separados por coma (Descarga se incluye siempre): ")
    pestañas = [p.strip() for p in entrada.split(",") if p.strip()]
    try:
        crear_usuario(usuario, clave, pestañas)
    except ErrorCuentas as exc:
        print(f"No se creó el usuario: {exc}")
        return 1
    print(f"Usuario {usuario} creado. Se le pedirá cambiar la clave en su primer acceso.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
