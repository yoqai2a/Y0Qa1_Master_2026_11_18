#!/usr/bin/env bash
# Publica en GitHub el control, el histórico y los NetCDF de un ciclo.
# Si otro proceso publicó antes (push rechazado), integra sus cambios y reintenta:
# en un conflicto de control.xlsx (binario) gana la versión remota y se vuelve a marcar este ciclo.
set -euo pipefail

: "${FECHA:?Falta FECHA}" "${CICLO:?Falta CICLO}"
RAMA="${GITHUB_REF_NAME:-$(git rev-parse --abbrev-ref HEAD)}"
CONTROL="___Data/control.xlsx"
MAX_INTENTOS=5

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

git add -f "$CONTROL"
shopt -s nullglob
for archivo in ___Data/___Historico/"${FECHA}_${CICLO}Z".*; do
  git add -f "$archivo"
done
for archivo in ___Data/___Historico_Corte/"${FECHA}_${CICLO}Z".*; do
  git add -f "$archivo"
done
# Las capas NetCDF del Corte temporal (76 por ciclo) se excluyen salvo que almacenamiento.json
# pida publicarlas: hacen crecer mucho el repositorio. El respaldo de perfiles sí se publica.
mapfile -t EXCLUIR < <(python .github/scripts/pathspec_corte.py)
git add -A -f ___Data/___NC "${EXCLUIR[@]}"

if git diff --cached --quiet; then
  echo "No hay cambios para publicar."
  exit 0
fi
git commit -m "Guardar NetCDF seleccionados, control e histórico ${FECHA} ${CICLO}Z"

for ((intento = 1; intento <= MAX_INTENTOS; intento++)); do
  if git push origin "HEAD:${RAMA}"; then
    echo "Publicado en el intento ${intento}."
    exit 0
  fi
  echo "Push rechazado (intento ${intento}/${MAX_INTENTOS}); se integran los cambios remotos."
  git fetch origin "${RAMA}"
  # En un rebase, "ours" es la rama remota sobre la que se reaplica nuestro commit.
  if ! git rebase -X ours "origin/${RAMA}"; then
    git rebase --abort || true
    echo "::error::No se pudo integrar la rama remota automáticamente." >&2
    exit 1
  fi
  python -m _Comun.control_ciclos marcar --ruta "$CONTROL" --fecha "$FECHA" --ciclo "$CICLO"
  git add -f "$CONTROL"
  if ! git diff --cached --quiet; then
    git commit --amend --no-edit
  fi
  sleep $((RANDOM % 6 + 2))
done

echo "::error::No se pudo publicar tras ${MAX_INTENTOS} intentos." >&2
exit 1
