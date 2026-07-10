"""Processamento batch das reuniões (rodar de madrugada via cron).

Para cada reunião com status 'processando':
  1. transcreve o áudio com faster-whisper (CPU/int8, pt) — passo pesado, por isso
     roda isolado de madrugada;
  2. gera a ata via DeepSeek (app.services.ata_service);
  3. grava transcricao + ata, status='concluida' e APAGA o .webm (mantém só o texto).

Em falha por reunião: rollback, status='erro' e log — não derruba o lote inteiro
(mesmo padrão de degradação graciosa de refresh_mednews).
"""
import logging
import os

from flask import current_app

from app.extensions import db
from app.models.reuniao import Reuniao
from app.services.ata_service import gerar_ata

logger = logging.getLogger(__name__)


def _load_whisper():
    """Carrega o modelo faster-whisper (import tardio: só existe na VPS)."""
    from faster_whisper import WhisperModel
    return WhisperModel('small', device='cpu', compute_type='int8')


def _transcrever(model, path):
    segments, _info = model.transcribe(path, language='pt', vad_filter=True)
    return ' '.join(seg.text.strip() for seg in segments).strip()


def processar_reunioes():
    """Processa todas as reuniões pendentes. Retorna um resumo {ok, erro}."""
    pendentes = Reuniao.query.filter_by(status='processando').all()
    if not pendentes:
        logger.info('Nenhuma reunião com status=processando.')
        return {'ok': 0, 'erro': 0}

    logger.info('Processando %d reunião(ões)…', len(pendentes))
    model = _load_whisper()  # carrega 1x por execução (economia de RAM)
    gravacoes_dir = current_app.config['GRAVACOES_DIR']
    result = {'ok': 0, 'erro': 0}

    for r in pendentes:
        try:
            if not r.arquivo_audio:
                raise FileNotFoundError(f'reunião {r.id} sem arquivo de áudio')
            path = os.path.join(gravacoes_dir, r.arquivo_audio)
            if not os.path.exists(path):
                raise FileNotFoundError(f'áudio não encontrado: {path}')

            transcricao = _transcrever(model, path)
            if not transcricao:
                raise ValueError('transcrição vazia (áudio sem fala reconhecível)')

            participantes = [p.medico.name for p in r.participantes if p.medico]
            ata = gerar_ata(
                transcricao,
                titulo=r.titulo,
                participantes=participantes,
                data=r.criada_em.strftime('%d/%m/%Y'),
            )

            r.transcricao = transcricao
            r.ata = ata
            r.status = 'concluida'
            db.session.commit()

            # Sucesso → apaga o .webm (mantém só transcrição + ata).
            try:
                os.remove(path)
            except OSError as exc:
                logger.warning('Não foi possível remover %s: %s', path, exc)

            result['ok'] += 1
            logger.info('Reunião %s concluída.', r.id)

        except Exception as exc:
            db.session.rollback()
            r.status = 'erro'
            db.session.commit()
            result['erro'] += 1
            logger.exception('Falha ao processar reunião %s: %s', r.id, exc)

    logger.info('Batch concluído: %s', result)
    return result
