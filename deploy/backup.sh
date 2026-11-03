#!/bin/bash
# Ежедневная копия базы и media. Хранит последние 7 копий в ~/backups
set -e
APP=/opt/library-system
DEST=$HOME/backups
STAMP=$(date +%F)
mkdir -p "$DEST"
sqlite3 "$APP/db.sqlite3" ".backup '$DEST/db-$STAMP.sqlite3'"
[ -d "$APP/media" ] && tar -czf "$DEST/media-$STAMP.tar.gz" -C "$APP" media
find "$DEST" -type f -mtime +7 -delete
