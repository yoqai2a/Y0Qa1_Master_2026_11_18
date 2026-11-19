# Visor Y0Qa1

La configuración de usuarios y permisos se carga desde el repositorio privado. Consulta el README de la raíz para definir `AUTH_GITHUB_REPO`, `AUTH_GITHUB_FILE`, `AUTH_GITHUB_BRANCH` y `AUTH_GITHUB_TOKEN` en los secretos del entorno. No guardes `accounts.json` ni tokens en este repositorio público.

Las pestañas Tablas, UV, Corte temporal, Plan y Descarga se muestran según los permisos que devuelva el archivo de cuentas privado. Tablas lee los NetCDF locales bajo `___Data/___NC` o, en Streamlit Cloud, el archivo comprimido `___Data/___Historico/YYYYMMDD_CCZ.csv.gz` guardado por el workflow para cada ciclo.

En Tablas, **Guardar histórico del ciclo** genera `___Data/___Historico/YYYYMMDD_CCZ.csv.gz` con todas las horas del ciclo para cada punto y las tres variables disponibles. Incluye área, punto, coordenadas, hora UTC, valor, unidad y archivo NetCDF de origen. La racha se guarda en km/h, la precipitación en mm y la isoterma 0 en m, sin la aproximación visual a centenas. Si se vuelve a guardar el mismo ciclo, se reemplaza su archivo con los datos actuales. GitHub Actions crea y publica automáticamente este histórico después de convertir un ciclo.
