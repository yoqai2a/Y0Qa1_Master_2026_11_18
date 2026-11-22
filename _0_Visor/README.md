# Visor Y0Qa1

La configuración de usuarios y permisos se carga desde el repositorio privado. Consulta el README de la raíz para definir `AUTH_GITHUB_REPO`, `AUTH_GITHUB_FILE`, `AUTH_GITHUB_BRANCH` y `AUTH_GITHUB_TOKEN` en los secretos del entorno. No guardes `accounts.json` ni tokens en este repositorio público.

Las pestañas Tablas, UV, Corte temporal, Plan y Descarga se muestran según los permisos que devuelva el archivo de cuentas privado. Tablas lee los NetCDF locales bajo `___Data/___NC` o, en Streamlit Cloud, el histórico `___Data/___Historico/YYYYMMDD_CCZ.parquet` guardado por el workflow para cada ciclo (también se leen los históricos anteriores `.csv.gz` y `.csv`).

## Organización del código

Cada pestaña tiene su propia carpeta con su código y su configuración:

| Ruta | Contenido |
|---|---|
| `Y0Qa1_Panel.py` | Archivo de entrada: acceso, sesión, pestañas y panel de descarga. |
| `accounts.py`, `limitador.py`, `errores.py` | Cuentas, límite de intentos de acceso y mensajes de error. |
| `tablas/` | **Pestaña Tablas.** `interfaz.py` (pantalla), `calculo.py` (períodos, máximos por área, series), `datos.py` (ciclos, NetCDF, histórico), `variables.py` (las 8 variables), `estilos.py` (paletas y leyendas), `pdf.py` (PDF imprimible) y `archivar_ciclo.py` (histórico del ciclo, lo usa el workflow). |
| `tablas/configuracion/` | `Puntos.json`, `cierres_tablas.json` y las paletas `rangos_*.json`. |
| `corte_temporal/` | **Pestaña Corte temporal**, con su propia `configuracion/` (ver su README). |
| `archivar_corte.py` | Respaldo de perfiles del Corte temporal (lo usa el workflow). |
| `../_Comun/` | Código compartido: `malla_nc.py` (puntos y celdas de la malla), `control_ciclos.py` (`control.xlsx`) y `registro.py` (logging). |

Para agregar o cambiar una variable de Tablas basta editar `tablas/variables.py`.

## Histórico por ciclo

Lo genera GitHub Actions después de convertir cada ciclo (o a mano con `python _0_Visor/tablas/archivar_ciclo.py --fecha AAAAMMDD --ciclo HH`; con `--formato csv` produce el CSV comprimido anterior). Contiene todas las horas del ciclo para cada punto y las ocho variables: racha, precipitación, isoterma 0, CAPE, temperatura máxima y mínima, base de nubes y visibilidad, con área, punto, coordenadas, hora UTC, valor, unidad y archivo NetCDF de origen. La racha se guarda en km/h; temperaturas en °C; base de nubes en ft; visibilidad en m; precipitación en mm; CAPE en J/kg; e isoterma 0 en m, sin la aproximación visual a centenas. Si se vuelve a generar el mismo ciclo, se reemplaza su archivo. Los históricos son un respaldo: no se borran automáticamente.

## Pestaña Tablas

- Los controles principales (ciclo, cierre UTC, variable, unidad y leyendas) están siempre visibles. **Acciones y exportación** agrupa guardar el cierre, crear el PDF y exportar a CSV o Excel (resumen por área y detalle de todos los puntos).
- Bajo los controles se indica el ciclo, el rango de horas de pronóstico disponible y la fecha del archivo.
- El PDF imprimible incluye los resúmenes por área de precipitación, CAPE, racha de viento e isoterma 0, con el ciclo y el cierre UTC elegidos. El cierre global predeterminado es 12Z.
- Las columnas diarias muestran `DD_MM_HHZ / DD_MM_HHZ` en UTC. La hora inicial es la hora posterior al cierre seleccionado: por ejemplo, cierre 12Z usa 13Z–12Z del día siguiente; cierre 03Z usa 04Z–03Z; cierre 00Z usa 01Z–00Z.
- La isoterma 0 puede mostrar el mínimo/máximo del período diario o, al activar el formato especial, los valores de 12Z y 00Z.
- CAPE usa rangos en J/kg; temperatura usa los límites y colores de `tablas/configuracion/rangos_temperatura.json`. Base de nubes y visibilidad comparten los colores y umbrales equivalentes: en base de nubes los umbrales se expresan en ft y la unidad predeterminada es ft; visibilidad se expresa en m.
- La precipitación es acumulada desde el inicio del ciclo. En períodos parciales se usa como base el primer valor disponible y como valor final el último disponible hasta el cierre.

## Acceso y sesión

- Tras 5 intentos fallidos seguidos para un usuario se bloquea el acceso temporalmente (30 s, que se duplica con cada fallo adicional hasta un máximo de 15 min). El bloqueo termina solo, y los fallos se olvidan tras 30 min o al ingresar correctamente.
- La sesión se cierra tras 120 minutos sin actividad (se cambia con `SESION_MAX_INACTIVIDAD_MIN` en los secretos).
- Los mensajes de error muestran un texto simple al usuario; el detalle técnico queda en el registro. El detalle se muestra automáticamente cuando abres el visor desde el mismo PC donde corre (localhost). Para verlo también en otros accesos, define `MOSTRAR_DETALLES_ERROR = "true"` en los secretos; con `"false"` se oculta siempre.

## Pestaña Corte temporal

Muestra, para un punto, un corte **tiempo × presión** de humedad relativa, temperatura o viento (rapidez con barbas, componente U o componente V), con todos los niveles de 1000 a 200 hPa. Se puede elegir ciclo, área, punto, vista, unidad (nudos, m/s o km/h para el viento), rango de presión y escala vertical (lineal o logarítmica), y descargar la imagen y los datos.

Todo su código y su configuración están en `corte_temporal/` (ver `corte_temporal/configuracion/README.md`). El respaldo de perfiles queda en `___Data/___Historico_Corte/AAAAMMDD_HHZ.parquet`; para rehacerlo con otros puntos: `python _0_Visor/archivar_corte.py --todos`.
