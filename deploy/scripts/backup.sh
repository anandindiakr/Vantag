#!/usr/bin/env bash
# Backup PostgreSQL for a given region
# Usage: ./backup.sh [india|singapore|malaysia]
set -euo pipefail

REGION="${1:-india}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/vantag}"
DATE=$(date +%Y%m%d_%H%M%S)

declare -A CONTAINER=(
    [india]="vantag_postgres_in"
    [singapore]="vantag_postgres_sg"
    [malaysia]="vantag_postgres_my"
)

declare -A DB_NAME=(
    [india]="vantag_in"
    [singapore]="vantag_sg"
    [malaysia]="vantag_my"
)

CONTAINER_NAME="${CONTAINER[$REGION]}"
DB="${DB_NAME[$REGION]}"
FILENAME="vantag_${REGION}_${DATE}.sql.gz"

mkdir -p "$BACKUP_DIR"

echo "Backing up $DB from $CONTAINER_NAME → $BACKUP_DIR/$FILENAME"
docker exec "$CONTAINER_NAME" pg_dump -U vantag "$DB" | gzip > "$BACKUP_DIR/$FILENAME"

# Keep last 30 backups
find "$BACKUP_DIR" -name "vantag_${REGION}_*.sql.gz" -mtime +30 -delete

echo "Backup complete: $BACKUP_DIR/$FILENAME"
ls -lh "$BACKUP_DIR/$FILENAME"
