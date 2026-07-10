"""Processa em batch as reuniões pendentes (transcrição + ata).

Rodar de madrugada via cron (ver scripts/processar_reunioes.sh). Requer as libs
`faster-whisper` (transcrição) e `DEEPSEEK_API_KEY` no .env (geração da ata).

Uso manual:
    .venv/bin/python scripts/processar_reunioes.py
"""
import os
import sys

# Ancora o import do pacote `app` na raiz do projeto, mesmo se o cwd variar.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.services.reuniao_processing import processar_reunioes


def main():
    app = create_app()
    with app.app_context():
        result = processar_reunioes()
        print(result)


if __name__ == '__main__':
    main()
