# Tokens necesarios para Y0Qa1

Se necesitan **dos Personal Access Tokens fine-grained**, separados y limitados a un solo repositorio cada uno. No uses tokens classic con permiso general `repo`.

## 1. `AUTH_GITHUB_TOKEN` — cuentas privadas

- **Nombre sugerido al crearlo:** `Y0Qa1-auth-priv`
- **Acceso a repositorios:** Only select repositories → `Y0Qa1_Master_2026_11_18_priv`
- **Repository permissions:** `Contents: Read and write`.
- **Uso:** leer `_0_Visor/accounts.json` y guardar cambios de claves desde el visor. Si no necesitas que el visor guarde cambios de clave, se puede reducir a `Contents: Read-only`, pero el cambio de clave de la app dejará de persistir.

## 2. `GITHUB_TOKEN` — descargas en el repositorio público

- **Nombre sugerido al crearlo:** `Y0Qa1-download-public`
- **Acceso a repositorios:** Only select repositories → `Y0Qa1_Master_2026_11_18`
- **Repository permissions:** `Actions: Read and write` y `Contents: Read-only`.
- **Uso:** iniciar el workflow `Get_fnnn.yml`, leer su historial y consultar `___Data/control.xlsx`.

GitHub incluye automáticamente un token temporal `GITHUB_TOKEN` dentro de cada ejecución de Actions. Ese token distinto ya está contemplado en el workflow para actualizar `control.xlsx`; **no lo tienes que crear ni pegar en Streamlit**.

## Crear cada token

En GitHub, abre **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**. Para cada uno:

1. Pon el nombre sugerido arriba y elige al propietario correcto.
2. Selecciona **Only select repositories** y marca solo el repo indicado.
3. Configura únicamente los permisos enumerados para ese token.
4. Elige una fecha de vencimiento y crea el token. GitHub lo muestra una sola vez: cópialo directamente a los secretos del visor.

El token de `AUTH_GITHUB_TOKEN` es de escritura porque el visor actualiza el JSON cuando una persona cambia su clave. GitHub requiere `Contents: write` para crear o actualizar un archivo; el token fino se puede restringir al repo privado. [Permisos de Contents](https://docs.github.com/en/rest/repos/contents). El inicio de workflow requiere `Actions: write`; leer los runs requiere `Actions: read`. [Permisos del API de Actions](https://docs.github.com/en/rest/actions/workflows).

## Dónde guardar los valores

**En este PC:** abre `%USERPROFILE%\.streamlit\secrets.toml` y pega la configuración TOML de abajo. Ese archivo está fuera de las carpetas de los repositorios.

**En Streamlit Community Cloud:** abre la app → **Settings → Secrets** y pega la misma configuración. Streamlit indica que los secretos se ingresan en la configuración privada de la app, no se suben al repositorio. [Secretos en Streamlit](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management).

```toml
AUTH_GITHUB_REPO = "TU_USUARIO/Y0Qa1_Master_2026_11_18_priv"
AUTH_GITHUB_FILE = "_0_Visor/accounts.json"
AUTH_GITHUB_BRANCH = "main"
AUTH_GITHUB_TOKEN = "PEGA_AQUI_EL_TOKEN_PRIVADO"

GITHUB_REPO = "TU_USUARIO/Y0Qa1_Master_2026_11_18"
GITHUB_TOKEN = "PEGA_AQUI_EL_TOKEN_PUBLICO"
GITHUB_WORKFLOW = "Get_fnnn.yml"
```

Reemplaza `TU_USUARIO` por tu usuario u organización de GitHub y los dos textos `PEGA_AQUI...` por el token correspondiente. No guardes los valores reales en `publicus`, `privatius`, en el código fuente ni en **Settings → Secrets and variables → Actions**: el visor los necesita como secretos de su propio proceso Streamlit. Si un token vence, crea uno nuevo y actualiza esta configuración.
