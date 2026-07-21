#!/bin/sh
set -eu
if [ "$#" -ne 1 ]; then
  echo "usage: scripts/restore-verify.sh /path/to/restored-makepdf.sqlite3" >&2
  exit 64
fi
exec python -m makepdf.web.maintenance verify "$1"
