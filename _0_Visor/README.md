# Visor Y0Qa1

El lanzador recomendado es `YoQa1_Visor.py` en la raíz. También se conserva `Y0Qa1_Panel.py` como entrada compatible. Para instalar dependencias y abrir el visor desde PowerShell:

```powershell
python -m pip install -r _0_Visor/requirements_panel.txt
python YoQa1_Visor.py
```

## Cuentas iniciales

El archivo `accounts.json` contiene las cuentas y sus permisos por pestaña. Todas empiezan con la clave provisoria `2026`; el visor obliga a cambiarla por una de al menos 8 caracteres antes de mostrar las pestañas. Las claves se guardan como hashes con sal, no en texto plano.

| Usuario | Pestañas |
|---|---|
| AAAAA | Descarga |
| BBBBB | Descarga, Tablas, UV |
| CCCCC | Descarga, Tablas, UV, Plan |
| DDDDD | Descarga, Tablas, UV, Corte temporal |
| EEEEE | Descarga, Tablas, UV, Corte temporal, Plan |

## Crear otra cuenta

Ejecuta desde PowerShell:

```powershell
python _0_Visor/crear_usuario.py
```

La utilidad pide nombre, clave provisoria y permisos. Siempre otorga `Descarga` y marca la clave para cambiarla en el primer ingreso. Conserva `accounts.json` junto al visor al copiarlo o publicarlo.

## GitHub Actions

Sin `GITHUB_TOKEN` y `GITHUB_REPO`, la pestaña Descarga abre en modo demostración y no inicia descargas. Para activar las descargas, define esas variables (por ejemplo en Streamlit Secrets o el entorno local). El token debe poder ejecutar Actions y leer Contents para consultar `___Data/control.xlsx`. Variables opcionales: `GITHUB_WORKFLOW`, `GITHUB_REF`, `GITHUB_CONTROL_PATH`.

La pestaña Tablas lee los NetCDF locales y las coordenadas agrupadas por área en `Puntos.json`. Permite consultar rachas (`gust`), precipitación total (`tp`, prefiere `msg597` y usa `tp_sfc` si cambia el número de mensaje) e isoterma 0 (`gh_iso0`, prefiere `msg416`). Resume por fecha y área, sin decimales. Selecciona una fila del resumen para ver los puntos del área y selecciona un punto para ver toda la serie de pronóstico, sin elegir un día. Para isoterma 0, el formato normal muestra mínimo / máximo del día; el control Formato especial muestra 12Z / 00Z del día siguiente. El día operativo empieza a las 04Z y termina al cierre elegido. El cierre global se guarda en `_0_Visor/cierres_tablas.json` y el botón Guardar cierre está en la fila de configuración, junto al menú desplegable Leyendas. Las rachas se convierten a km/h, kt o m/s (km/h por defecto). La paleta de viento se define en km/h y sus umbrales y leyenda cambian a la unidad elegida. La precipitación acumulada desde el inicio del ciclo se diferencia para obtener el total diario en mm. Los rangos cromáticos editables están en `rangos_viento.json` y `rangos_precipitacion.json`; el archivo de precipitación define paletas específicas por área y las áreas sin paleta (gris claro con letras negras). La isoterma no usa paleta. Requiere `netCDF4` (incluido en `requirements_panel.txt`).

En Tablas, **Guardar histórico del ciclo** genera `___Data/___Historico/YYYYMMDD_CCZ.csv` con todas las horas del ciclo para cada punto y las tres variables disponibles. Incluye área, punto, coordenadas, hora UTC, valor, unidad y archivo NetCDF de origen. La racha se guarda en km/h, la precipitación en mm y la isoterma 0 en m, sin la aproximación visual a centenas. Si se vuelve a guardar el mismo ciclo, se reemplaza su CSV con los datos actuales.

Las pestañas UV, Corte temporal y Plan quedan visibles según permisos; por ahora muestran un espacio preparado para incorporar su contenido.
