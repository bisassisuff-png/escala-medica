#!/bin/bash
# Atualiza cache MedNews — roda diariamente às 5h via cron.
set -e

PROJECT_DIR="/root/projetos/escala-medica"
LOG_FILE="$PROJECT_DIR/logs/mednews.log"

mkdir -p "$PROJECT_DIR/logs"

cd "$PROJECT_DIR"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Iniciando atualização MedNews..." >> "$LOG_FILE"

FLASK_APP=run.py FLASK_ENV=development \
  .venv/bin/flask mednews-refresh >> "$LOG_FILE" 2>&1

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Concluído." >> "$LOG_FILE"
