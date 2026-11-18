"""Lanza el visor local incluido en _0_Visor."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


RAIZ = Path(__file__).resolve().parent
APP = RAIZ / "_0_Visor" / "Y0Qa1_Panel.py"


def main() -> int:
    if not APP.is_file():
        print(f"No se encontró el visor: {APP}", file=sys.stderr)
        return 2
    comando = [
        sys.executable, "-m", "streamlit", "run", str(APP),
        "--server.address=127.0.0.1", "--server.port=8501", "--server.headless=false",
        "--theme.base=dark", "--theme.backgroundColor=#111827",
        "--theme.secondaryBackgroundColor=#1F2937", "--theme.textColor=#F9FAFB",
    ]
    return subprocess.call(comando, cwd=RAIZ)


if __name__ == "__main__":
    raise SystemExit(main())
