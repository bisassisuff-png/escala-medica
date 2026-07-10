"""Módulo de reuniões virtuais com gravação (no host) e ata automática.

- Criação/gestão: somente admin (host = admin criador).
- Entrada na sala / visualização da ata: host, participantes ou admin.
- Gravação: apenas o host envia chunks de áudio; o arquivo é anexado em
  gravacoes/reuniao_<id>.webm (fora de qualquer pasta pública).
- Transcrição + ata rodam em batch de madrugada (scripts/processar_reunioes.py).

Reutiliza a autenticação existente (Flask-Login) e os decorators do projeto.
Endpoints POST chamados via fetch esperam o header X-CSRFToken (CSRFProtect global).
"""
import os
import logging

from flask import (Blueprint, render_template, redirect, url_for, flash,
                   request, abort, jsonify, current_app)
from flask_login import login_required, current_user

from app.extensions import db
from app.models.user import User
from app.models.reuniao import Reuniao, ReuniaoParticipante
from app.utils.decorators import admin_required

logger = logging.getLogger(__name__)

reuniao_bp = Blueprint('reuniao', __name__, url_prefix='/reuniao')

# Status em que a reunião ainda aceita chunks de áudio.
STATUS_GRAVAVEIS = ('aberta', 'gravando')


@reuniao_bp.before_request
def _bloqueia_se_desativado():
    """Feature flag: enquanto REUNIOES_ENABLED for falso, o módulo fica inacessível
    (mesmo por URL direta) e mostra uma página 'em breve'."""
    if not current_app.config.get('REUNIOES_ENABLED'):
        return render_template('reuniao/desativado.html'), 200


def _get_reuniao_or_404(reuniao_id):
    reuniao = db.session.get(Reuniao, reuniao_id)
    if reuniao is None:
        abort(404)
    return reuniao


def _gravacoes_dir():
    """Diretório das gravações, criado com permissão 700 se necessário."""
    path = current_app.config['GRAVACOES_DIR']
    os.makedirs(path, mode=0o700, exist_ok=True)
    return path


def _audio_path(reuniao):
    return os.path.join(_gravacoes_dir(), f'reuniao_{reuniao.id}.webm')


# ── Listagem ────────────────────────────────────────────────────────────────

@reuniao_bp.route('/')
@login_required
def lista():
    if current_user.is_admin:
        reunioes = Reuniao.query.order_by(Reuniao.criada_em.desc()).all()
    else:
        # Médico vê as reuniões em que é participante.
        reunioes = (Reuniao.query
                    .join(ReuniaoParticipante,
                          ReuniaoParticipante.reuniao_id == Reuniao.id)
                    .filter(ReuniaoParticipante.medico_id == current_user.id)
                    .order_by(Reuniao.criada_em.desc())
                    .all())
    return render_template('reuniao/lista.html', reunioes=reunioes)


# ── Criação (somente admin) ─────────────────────────────────────────────────

@reuniao_bp.route('/criar', methods=['GET', 'POST'])
@login_required
@admin_required
def criar():
    medicos = (User.query
               .filter_by(active=True)
               .filter(User.role.in_(('medico', 'admin')))
               .order_by(User.name)
               .all())

    if request.method == 'POST':
        titulo = (request.form.get('titulo') or '').strip()
        participante_ids = request.form.getlist('participantes')
        if not titulo:
            flash('Informe um título para a reunião.', 'danger')
            return render_template('reuniao/criar.html', medicos=medicos)

        reuniao = Reuniao(titulo=titulo, criada_por=current_user.id, status='aberta')
        db.session.add(reuniao)
        db.session.flush()  # garante reuniao.id

        vistos = set()
        for pid in participante_ids:
            try:
                pid = int(pid)
            except (TypeError, ValueError):
                continue
            if pid in vistos:
                continue
            vistos.add(pid)
            db.session.add(ReuniaoParticipante(reuniao_id=reuniao.id, medico_id=pid))

        db.session.commit()
        flash('Reunião criada.', 'success')
        return redirect(url_for('reuniao.sala', reuniao_id=reuniao.id))

    return render_template('reuniao/criar.html', medicos=medicos)


# ── Sala de vídeo ───────────────────────────────────────────────────────────

@reuniao_bp.route('/<int:reuniao_id>/sala')
@login_required
def sala(reuniao_id):
    reuniao = _get_reuniao_or_404(reuniao_id)
    if not reuniao.pode_ver(current_user):
        abort(403)
    return render_template('reuniao/sala.html',
                           reuniao=reuniao,
                           is_host=reuniao.is_host(current_user.id))


@reuniao_bp.route('/entrar', methods=['POST'])
@login_required
def entrar():
    """Gera um token de acesso LiveKit para a sala da reunião."""
    reuniao_id = request.form.get('reuniao_id', type=int)
    if reuniao_id is None:
        return jsonify(error='reuniao_id ausente'), 400
    reuniao = _get_reuniao_or_404(reuniao_id)
    if not reuniao.pode_ver(current_user):
        abort(403)

    api_key = current_app.config.get('LIVEKIT_API_KEY')
    api_secret = current_app.config.get('LIVEKIT_API_SECRET')
    ws_url = current_app.config.get('LIVEKIT_WS_URL')
    if not (api_key and api_secret and ws_url):
        logger.error('LiveKit não configurado (.env)')
        return jsonify(error='LiveKit não configurado no servidor'), 503

    # Import tardio: o pacote só existe na VPS após `pip install livekit-api`.
    try:
        from livekit import api as lk_api
    except ImportError:
        logger.error('livekit-api não instalado')
        return jsonify(error='livekit-api não instalado no servidor'), 503

    token = (lk_api.AccessToken(api_key, api_secret)
             .with_identity(str(current_user.id))
             .with_name(current_user.name)
             .with_grants(lk_api.VideoGrants(
                 room_join=True,
                 room=reuniao.room_name,
                 can_publish=True,
                 can_subscribe=True,
             ))
             .to_jwt())

    return jsonify(token=token, ws_url=ws_url, room=reuniao.room_name,
                   is_host=reuniao.is_host(current_user.id))


# ── Controle de gravação (somente host) ─────────────────────────────────────

def _require_host(reuniao):
    if not reuniao.is_host(current_user.id):
        abort(403)


@reuniao_bp.route('/<int:reuniao_id>/iniciar', methods=['POST'])
@login_required
def iniciar_gravacao(reuniao_id):
    reuniao = _get_reuniao_or_404(reuniao_id)
    _require_host(reuniao)
    if reuniao.status in ('processando', 'concluida'):
        return jsonify(error='reunião já encerrada'), 409
    reuniao.status = 'gravando'
    db.session.commit()
    return jsonify(status=reuniao.status)


@reuniao_bp.route('/<int:reuniao_id>/encerrar', methods=['POST'])
@login_required
def encerrar_gravacao(reuniao_id):
    reuniao = _get_reuniao_or_404(reuniao_id)
    _require_host(reuniao)
    reuniao.status = 'processando'
    db.session.commit()
    return jsonify(status=reuniao.status)


@reuniao_bp.route('/chunk', methods=['POST'])
@login_required
def chunk():
    """Recebe um chunk de áudio do host e o anexa ao arquivo da reunião."""
    reuniao_id = request.form.get('reuniao_id', type=int)
    seq = request.form.get('seq', type=int)
    if reuniao_id is None or seq is None:
        return jsonify(error='reuniao_id/seq ausentes'), 400

    reuniao = _get_reuniao_or_404(reuniao_id)
    _require_host(reuniao)

    if reuniao.status not in STATUS_GRAVAVEIS:
        return jsonify(error=f'reunião não está gravando (status={reuniao.status})'), 409

    blob = request.files.get('chunk')
    if blob is None:
        return jsonify(error='arquivo de chunk ausente'), 400

    path = _audio_path(reuniao)
    # Append binário: o cliente envia os chunks em ordem (fila sequencial).
    with open(path, 'ab') as f:
        f.write(blob.read())

    if not reuniao.arquivo_audio:
        reuniao.arquivo_audio = os.path.basename(path)
        db.session.commit()

    return jsonify(ok=True, seq=seq)


# ── Ata ─────────────────────────────────────────────────────────────────────

@reuniao_bp.route('/<int:reuniao_id>/ata')
@login_required
def ata(reuniao_id):
    reuniao = _get_reuniao_or_404(reuniao_id)
    if not reuniao.pode_ver(current_user):
        abort(403)
    return render_template('reuniao/ata.html', reuniao=reuniao)
