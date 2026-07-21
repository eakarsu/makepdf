#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_root="${RUNTIME_PROJECT_SOURCE:-$script_dir}"
cd "$project_root"
python_bin=python
if [[ -x "$project_root/.venv/bin/python" ]]; then
  python_bin="$project_root/.venv/bin/python"
fi

mode="${1:-api}"
case "$mode" in
  check)
    exec "$python_bin" -m makepdf.web.check
    ;;
  api)
    runtime_port="${PORT:-}"
    if [[ ! "$runtime_port" =~ ^[0-9]+$ ]] || (( runtime_port < 1024 || runtime_port > 65535 )); then
      echo "ERROR: PORT must be an explicitly assigned numeric port between 1024 and 65535." >&2
      exit 1
    fi
    if lsof -tiTCP:"$runtime_port" -sTCP:LISTEN >/dev/null 2>&1; then
      echo "ERROR: assigned port $runtime_port is already occupied." >&2
      exit 1
    fi
    export MAKEPDF_HOST=127.0.0.1 MAKEPDF_PORT="$runtime_port"
    if [[ "${NODE_ENV:-production}" != production ]]; then
      export MAKEPDF_ENV=development
      export API_KEY="${API_KEY:-${ADMIN_PASSWORD:-}}"
      export MAKEPDF_TENANT_ID="${MAKEPDF_TENANT_ID:-${TENANT_ID:-runtime-tenant}}"
      export MAKEPDF_USER_ID="${MAKEPDF_USER_ID:-${ADMIN_EMAIL:-runtime-admin}}"
      export MAKEPDF_ROLE="${MAKEPDF_ROLE:-administrator}"
      export MAKEPDF_DATA_DIR="${MAKEPDF_DATA_DIR:-${DB_PATH:-$project_root/.runtime/makepdf.sqlite}.data}"
      export MAKEPDF_JOB_DB="${MAKEPDF_JOB_DB:-$MAKEPDF_DATA_DIR/service.sqlite3}"
      export MAKEPDF_OBJECT_DIR="${MAKEPDF_OBJECT_DIR:-$MAKEPDF_DATA_DIR/objects}"
      export MAKEPDF_API_WORKERS=1
    fi
    "$python_bin" -m makepdf.web.check
    exec "$python_bin" -m uvicorn makepdf.web.app:app --host 127.0.0.1 --port "$runtime_port" --workers "${MAKEPDF_API_WORKERS:-2}"
    ;;
  worker)
    "$python_bin" -m makepdf.web.check
    exec "$python_bin" -m makepdf.web.worker
    ;;
  *)
    echo "usage: ./start.sh check|api|worker" >&2
    exit 64
    ;;
esac
