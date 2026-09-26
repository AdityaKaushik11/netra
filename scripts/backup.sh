#!/bin/sh
# Consistent MySQL dump (InnoDB single transaction), gzipped, keeping the last 7 days.
set -e
cd "$(dirname "$0")/.."
DEST="${BACKUP_DIR:-$HOME/netra-backups}"
mkdir -p "$DEST" && chmod 700 "$DEST"
FILE="$DEST/netra-$(date +%Y%m%d-%H%M).sql.gz"
sudo docker compose exec -T mysql sh -c \
  'exec mysqldump --single-transaction --quick --no-tablespaces -unetra -p"$MYSQL_PASSWORD" netra' | gzip > "$FILE"
find "$DEST" -name 'netra-*.sql.gz' -mtime +7 -delete
echo "$(date -Is) backup written: $FILE ($(du -h "$FILE" | cut -f1))"
