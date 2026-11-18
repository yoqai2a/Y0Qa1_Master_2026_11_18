# Visor Y0Qa1

La configuración de usuarios y permisos se carga desde el repositorio privado. Consulta el README de la raíz para definir `AUTH_GITHUB_REPO`, `AUTH_GITHUB_FILE`, `AUTH_GITHUB_BRANCH` y `AUTH_GITHUB_TOKEN` en los secretos del entorno. No guardes `accounts.json` ni tokens en este repositorio público.

Las pestañas Tablas, UV, Corte temporal, Plan y Descarga se muestran según los permisos que devuelva el archivo de cuentas privado. Las tablas leen los NetCDF locales bajo `___Data/___NC`; el workflow de GitHub Actions descarga y crea esos NetCDF.
