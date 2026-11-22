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
python -m pip install -r _0_Visor/requirements.txt
python Y0Qa1_Visor.py
```

Para ejecutar también la descarga y la creación de NetCDF en tu PC (`_1_Y0Qa1_GetFnnn.py`, `_2_Y0Qa1_CreaNC.py`) instala además las dependencias del workflow: `python -m pip install -r requirements.txt` (incluye `pygrib`).

Para desplegar el visor en Streamlit Community Cloud, usa `_0_Visor/Y0Qa1_Panel.py` como archivo de entrada y agrega los mismos valores en los secretos de la aplicación. Cloud instala las dependencias de `_0_Visor/requirements.txt` (la que está junto al archivo de entrada).

Los programas de línea de comandos escriben su registro con `logging`; el nivel se cambia con la variable de entorno `Y0QA1_LOG` (`DEBUG`, `INFO`, `WARNING`).

## Datos NetCDF

El workflow guarda el control de ciclos en `___Data/control.xlsx`, los históricos por ciclo en `___Data/___Historico/YYYYMMDD_CCZ.parquet` (respaldo que no se borra solo; los `.csv.gz` anteriores se siguen leyendo) y los NetCDF habilitados en `_2_CreaNC/seleccion_nc.json`. El control registra una fila por fecha y columnas para 00, 06, 12 y 18 UTC. La selección guarda `gust_sfc`, `tp_sfc`, `gh_iso0`, `cape_sfc`, `tmax_2m`, `tmin_2m`, `gh_ceiling` y `vis_sfc`; las demás variables permanecen desactivadas. Se conservan 10 ciclos de seis horas (aproximadamente 60 horas) en la carpeta `___Data/___NC`.

El archivo JSON enumera las variables NetCDF disponibles. Cambia cada valor de `archivos` a `true` o `false`; los ausentes se consideran desactivados. La limpieza retira ciclos antiguos del árbol actual del repositorio, aunque Git mantiene sus objetos en el historial de commits.

El workflow también se programa diariamente a las 04:20, 10:20, 16:20 y 22:20 UTC. Cada ejecución automática procesa el ciclo 00Z, 06Z, 12Z o 18Z correspondiente, respectivamente.

Para ciclos descargados antes de esta modificación, vuelve a iniciar ese ciclo una vez marcando **Forzar aunque control.xlsx indique que ya existe**. El workflow regenerará el ciclo y publicará su histórico; las descargas nuevas lo publican automáticamente.

## Workflow de GitHub Actions

- Las ejecuciones se hacen una a la vez (grupo de concurrencia único) y el script `.github/scripts/publicar.sh` reintenta la publicación si otro proceso publicó antes, integrando su `control.xlsx` sin perder ciclos.
- En las ejecuciones programadas, si GitHub retrasa el cron más allá de la medianoche UTC, la fecha del ciclo se calcula hacia atrás (el ciclo 18Z que corre a las 00:30 queda con la fecha del día anterior).
- La fecha escrita a mano se valida antes de instalar nada (formato `AAAAMMDD`, fecha real y no futura).
- Si el job falla se abre un Issue por ciclo (o se comenta en el que ya está abierto).
- Las acciones están fijadas por SHA de commit; para actualizarlas, cambia el SHA y el comentario con la versión.
- Pestaña **Corte temporal**: el workflow crea 76 capas NetCDF más por ciclo (temperatura, humedad y viento u, v en 19 niveles; ver `_0_Visor/corte_temporal/configuracion/`) y guarda un respaldo compacto de perfiles en `___Data/___Historico_Corte/`. Por defecto **no** sube esas capas a GitHub (`publicar_nc_en_git` en `almacenamiento.json`), porque harían crecer mucho el repositorio.
