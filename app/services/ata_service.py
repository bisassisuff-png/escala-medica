"""Geração da ata de reunião a partir da transcrição, via LLM DeepSeek.

DeepSeek expõe uma API compatível com a da OpenAI (`/chat/completions`), então
usamos apenas `requests` (já é dependência do projeto) — sem SDK novo. A key vem
do `.env` (`DEEPSEEK_API_KEY`), nunca hardcoded.

Uso:
    from app.services.ata_service import gerar_ata
    ata = gerar_ata(transcricao, titulo=..., participantes=[...], data=...)
"""
import logging

import requests
from flask import current_app

logger = logging.getLogger(__name__)

DEEPSEEK_URL = 'https://api.deepseek.com/chat/completions'
MODEL = 'deepseek-chat'
TIMEOUT = 120  # a chamada LLM é leve em RAM, mas pode demorar; roda no batch

SYSTEM_PROMPT = (
    'Você é um secretário executivo que redige atas de reunião formais em '
    'português do Brasil. Recebe a transcrição bruta (gerada por reconhecimento '
    'de fala, podendo conter erros) de uma reunião médica e produz uma ata clara, '
    'objetiva e em linguagem formal. Use EXATAMENTE as seções abaixo, nesta ordem, '
    'como títulos em markdown:\n'
    '## Data\n## Participantes\n## Pauta\n## Principais pontos discutidos\n'
    '## Decisões tomadas\n## Pendências e responsáveis\n## Próximos passos\n\n'
    'Regras: seja fiel à transcrição; NÃO invente fatos, nomes ou decisões. Se uma '
    'seção não tiver informação clara na transcrição, escreva "Não especificado." '
    'Não inclua a transcrição bruta na resposta.'
)


class AtaError(Exception):
    """Falha ao gerar a ata (rede, API, resposta inválida ou key ausente)."""


def gerar_ata(transcricao, titulo=None, participantes=None, data=None):
    """Gera a ata estruturada a partir da transcrição. Lança AtaError em falha.

    `participantes` é uma lista de nomes (opcional) e `data` uma string (opcional),
    passadas como contexto ao modelo — a transcrição continua sendo a fonte de verdade.
    """
    api_key = current_app.config.get('DEEPSEEK_API_KEY')
    if not api_key:
        raise AtaError('DEEPSEEK_API_KEY ausente no ambiente/.env')

    if not transcricao or not transcricao.strip():
        raise AtaError('transcrição vazia — nada a resumir')

    contexto = []
    if titulo:
        contexto.append(f'Título da reunião: {titulo}')
    if data:
        contexto.append(f'Data: {data}')
    if participantes:
        contexto.append('Participantes convidados: ' + ', '.join(participantes))
    cabecalho = ('\n'.join(contexto) + '\n\n') if contexto else ''

    user_prompt = (
        f'{cabecalho}Transcrição da reunião:\n"""\n{transcricao.strip()}\n"""\n\n'
        'Redija a ata seguindo estritamente as seções e regras definidas.'
    )

    payload = {
        'model': MODEL,
        'messages': [
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': user_prompt},
        ],
        'temperature': 0.2,
        'stream': False,
    }
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }

    try:
        resp = requests.post(DEEPSEEK_URL, json=payload, headers=headers, timeout=TIMEOUT)
        resp.raise_for_status()
        data_json = resp.json()
        content = data_json['choices'][0]['message']['content'].strip()
    except requests.RequestException as exc:
        raise AtaError(f'erro de rede/API DeepSeek: {exc}') from exc
    except (KeyError, IndexError, ValueError) as exc:
        raise AtaError(f'resposta inesperada da DeepSeek: {exc}') from exc

    if not content:
        raise AtaError('DeepSeek retornou conteúdo vazio')
    return content
