# Y0Qa1 · repositorio público

Este repositorio contiene el código del visor y los workflows de descarga. Las cuentas y sus permisos se guardan en el repositorio privado `privatius`; no copies allí `accounts.json`, tokens ni `secrets.toml`.

## Configuración de los dos repositorios

La lista de tokens, sus permisos exactos y el lugar donde guardarlos está en [TOKENS_Y0QA1.md](TOKENS_Y0QA1.md).

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

El workflow guarda el control de ciclos en `___Data/control.xlsx`, los históricos comprimidos por ciclo en `___Data/___Historico/YYYYMMDD_CCZ.csv.gz` y los NetCDF habilitados en `_2_CreaNC/seleccion_nc.json`. El control registra una fila por fecha y columnas para 00, 06, 12 y 18 UTC. La selección guarda `gust_sfc`, `tp_sfc`, `gh_iso0`, `cape_sfc`, `tmax_2m`, `tmin_2m`, `gh_ceiling` y `vis_sfc`; las demás variables permanecen desactivadas. Se conservan 10 ciclos de seis horas (aproximadamente 60 horas) en la carpeta `___Data/___NC`.

El archivo JSON enumera las variables NetCDF disponibles. Cambia cada valor de `archivos` a `true` o `false`; los ausentes se consideran desactivados. La limpieza retira ciclos antiguos del árbol actual del repositorio, aunque Git mantiene sus objetos en el historial de commits.

El workflow también se programa diariamente a las 04:20, 10:20, 16:20 y 22:20 UTC. Cada ejecución automática procesa el ciclo 00Z, 06Z, 12Z o 18Z correspondiente, respectivamente.

Para ciclos descargados antes de esta modificación, vuelve a iniciar ese ciclo una vez marcando **Forzar aunque control.xlsx indique que ya existe**. El workflow regenerará el ciclo y publicará su histórico; las descargas nuevas lo publican automáticamente.
