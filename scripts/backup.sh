#!/bin/sh
set -eu
if [ "$#" -ne 1 ]; then
  echo "usage: scripts/backup.sh /encrypted-backup-volume/makepdf.sqlite3" >&2
  exit 64
fi
exec python -m makepdf.web.maintenance backup "$1"
