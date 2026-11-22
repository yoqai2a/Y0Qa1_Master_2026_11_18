"""Límite de intentos de inicio de sesión con bloqueo temporal y creciente.

No bloquea para siempre: tras ``max_fallos`` fallos seguidos se bloquea un rato, que se duplica
con cada fallo adicional hasta un tope (``tope_s``). El bloqueo termina solo, y los fallos se
olvidan por completo tras ``olvido_s`` sin actividad o al ingresar correctamente.

Es lógica pura (sin Streamlit) para poder probarla.
"""
from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from typing import Callable


@dataclass
class _Estado:
    fallos: int = 0
    ultimo_fallo: float = 0.0
    bloqueado_hasta: float = 0.0


class LimitadorIntentos:
    def __init__(self, max_fallos: int = 5, base_s: float = 30.0, tope_s: float = 900.0,
                 olvido_s: float = 1800.0, max_claves: int = 5000,
                 reloj: Callable[[], float] = time.monotonic) -> None:
        self.max_fallos = max_fallos
        self.base_s = base_s
        self.tope_s = tope_s
        self.olvido_s = olvido_s
        self.max_claves = max_claves
        self._reloj = reloj
        self._estados: dict[str, _Estado] = {}
        self._cerrojo = threading.Lock()

    @staticmethod
    def normalizar(clave: str) -> str:
        return str(clave).strip().upper()[:64]

    def _vigente(self, clave: str, ahora: float) -> _Estado | None:
        estado = self._estados.get(clave)
        if estado is None:
            return None
        if ahora - estado.ultimo_fallo > self.olvido_s and ahora >= estado.bloqueado_hasta:
            del self._estados[clave]
            return None
        return estado

    def segundos_restantes(self, clave: str) -> int:
        """Segundos que faltan para poder reintentar (0 si no está bloqueado)."""
        clave = self.normalizar(clave)
        ahora = self._reloj()
        with self._cerrojo:
            estado = self._vigente(clave, ahora)
            if estado is None:
                return 0
            return max(0, math.ceil(estado.bloqueado_hasta - ahora))

    def registrar_fallo(self, clave: str) -> int:
        """Anota un fallo; devuelve los segundos de bloqueo resultantes (0 si aún no bloquea)."""
        clave = self.normalizar(clave)
        ahora = self._reloj()
        with self._cerrojo:
            if len(self._estados) >= self.max_claves:
                self._podar(ahora)
            estado = self._vigente(clave, ahora) or self._estados.setdefault(clave, _Estado())
            estado.fallos += 1
            estado.ultimo_fallo = ahora
            if estado.fallos >= self.max_fallos:
                espera = min(self.tope_s, self.base_s * 2 ** (estado.fallos - self.max_fallos))
                estado.bloqueado_hasta = ahora + espera
                return math.ceil(espera)
            return 0

    def registrar_exito(self, clave: str) -> None:
        with self._cerrojo:
            self._estados.pop(self.normalizar(clave), None)

    def intentos_restantes(self, clave: str) -> int:
        """Fallos que quedan antes del primer bloqueo."""
        clave = self.normalizar(clave)
        with self._cerrojo:
            estado = self._vigente(clave, self._reloj())
            return max(0, self.max_fallos - (estado.fallos if estado else 0))

    def _podar(self, ahora: float) -> None:
        for clave in [k for k, e in self._estados.items()
                      if ahora - e.ultimo_fallo > self.olvido_s and ahora >= e.bloqueado_hasta]:
            del self._estados[clave]
        # Si siguen siendo demasiadas, descarta las más antiguas.
        exceso = len(self._estados) - self.max_claves + 1
        if exceso > 0:
            for clave, _ in sorted(self._estados.items(), key=lambda kv: kv[1].ultimo_fallo)[:exceso]:
                del self._estados[clave]


def texto_espera(segundos: int) -> str:
    """'45 segundos', '2 minutos'..."""
    if segundos < 60:
        return f"{segundos} segundo{'s' if segundos != 1 else ''}"
    minutos = math.ceil(segundos / 60)
    return f"{minutos} minuto{'s' if minutos != 1 else ''}"
