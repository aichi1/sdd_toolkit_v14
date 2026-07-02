#!/usr/bin/env bash
# PostToolUse hook: フェーズ完了時にコンポーネント候補を自動抽出する

PROJECT_ROOT="${1:-.}"
SCRIPTS_DIR="${PROJECT_ROOT}/scripts"
KB_DIR="${HOME}/.sdd-knowledge"

EXTRACT_SCRIPT=""
if [ -f "${SCRIPTS_DIR}/extract_components.py" ]; then
    EXTRACT_SCRIPT="${SCRIPTS_DIR}/extract_components.py"
elif [ -f "${PROJECT_ROOT}/outputs/phase-02/src/extract_components.py" ]; then
    EXTRACT_SCRIPT="${PROJECT_ROOT}/outputs/phase-02/src/extract_components.py"
fi

if [ -z "${EXTRACT_SCRIPT}" ]; then
    echo "[hook] extract_components.py not found, skipping" >&2
    exit 0
fi

PROJECT_NAME=$(basename "${PROJECT_ROOT}")
echo "[hook] Extracting component candidates from ${PROJECT_NAME}..."
python3 "${EXTRACT_SCRIPT}" "${PROJECT_ROOT}" --project-name "${PROJECT_NAME}" --kb-dir "${KB_DIR}" 2>&1 || true
echo "[hook] Done."
