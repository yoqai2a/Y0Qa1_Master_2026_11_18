# Y0Qa1 · repositorio público

Este repositorio contiene el código del visor y los workflows de descarga. Las cuentas y sus permisos se guardan en el repositorio privado `privatius`; no copies allí `accounts.json`, tokens ni `secrets.toml`.

## Configuración de los dos repositorios

En la configuración privada del entorno Streamlit (o en `%USERPROFILE%\.streamlit\secrets.toml` para uso local) define:

```toml
AUTH_GITHUB_REPO = "TU_USUARIO/Y0Qa1_Master_2026_11_18_priv"
AUTH_GITHUB_FILE = "_0_Visor/accounts.json"
AUTH_GITHUB_BRANCH = "main"
AUTH_GITHUB_TOKEN = "TOKEN_FG_PRIVATIUS"

GITHUB_REPO = "TU_USUARIO/Y0Qa1_Master_2026_11_18"
GITHUB_TOKEN = "TOKEN_FG_PUBLICUS"
GITHUB_WORKFLOW = "Get_fnnn.yml"
```

`TOKEN_FG_PRIVATIUS` debe ser un token fine-grained limitado al repo privado, con Contents: read y write. La escritura permite guardar cambios de clave desde el visor. `TOKEN_FG_PUBLICUS` debe limitarse al repo público y contar con Actions: write y Contents: read para consultar `___Data/control.xlsx`. Mantén ambos tokens fuera de Git y no los pegues en esta plantilla.

El archivo privado `accounts.json` contiene hashes con sal y permisos por pestaña. Cada cambio de clave escribe una nueva versión en el historial del repo privado; el visor nunca guarda claves en texto plano.

## Abrir localmente

Instala las dependencias desde PowerShell, con esta carpeta como directorio actual:

```powershell
python -m pip install -r requirements.txt
python -m pip install -r _0_Visor/requirements_panel.txt
python YoQa1_Visor.py
```

Para desplegar el visor en Streamlit Community Cloud, usa `_0_Visor/Y0Qa1_Panel.py` como archivo de entrada y agrega los mismos valores en los secretos de la aplicación.

## Datos NetCDF

El workflow guarda el control de ciclos en `___Data/control.xlsx`. Los NetCDF, archivos GRIB e históricos generados localmente se excluyen del repositorio; se crean en `___Data` al ejecutar descargas y conversiones.
