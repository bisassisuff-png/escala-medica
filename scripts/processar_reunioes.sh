#!/bin/bash
# Processa reuniões pendentes (transcrição faster-whisper + ata DeepSeek).
# Roda de madrugada via cron — nunca durante a reunião (restrição de RAM da VPS).
#   Cron sugerido (3h da manhã):
#     0 3 * * * /root/projetos/escala-medica/scripts/processar_reunioes.sh
set -e

PROJECT_DIR="/root/projetos/escala-medica"
LOG_FILE="$PROJECT_DIR/logs/reunioes.log"

mkdir -p "$PROJECT_DIR/logs"

cd "$PROJECT_DIR"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Iniciando processamento de reuniões..." >> "$LOG_FILE"

.venv/bin/python scripts/processar_reunioes.py >> "$LOG_FILE" 2>&1

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Concluído." >> "$LOG_FILE"
