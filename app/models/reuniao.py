from datetime import datetime
from app.extensions import db
import sqlalchemy as sa


class Reuniao(db.Model):
    """Reunião virtual remota com gravação de áudio (no host) e ata automática.

    Fluxo de status:
      aberta → gravando → processando → concluida  (ou → erro no batch)
    A sala LiveKit correspondente tem nome `reuniao_<id>`.
    """
    __tablename__ = 'reunioes'

    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(300), nullable=False)
    criada_por = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    criada_em = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    arquivo_audio = db.Column(db.String(500))          # nome do .webm em gravacoes/
    transcricao = db.Column(db.Text)                   # preenchida no batch
    ata = db.Column(db.Text)                           # preenchida no batch (LLM)
    status = db.Column(
        sa.Enum('aberta', 'gravando', 'processando', 'concluida', 'erro',
                name='reuniao_status'),
        default='aberta', nullable=False
    )

    criador = db.relationship('User', foreign_keys=[criada_por])
    participantes = db.relationship(
        'ReuniaoParticipante', back_populates='reuniao',
        cascade='all, delete-orphan', passive_deletes=True
    )

    @property
    def room_name(self):
        return f'reuniao_{self.id}'

    def is_host(self, user_id):
        return self.criada_por == int(user_id)

    def participante_ids(self):
        return {p.medico_id for p in self.participantes}

    def pode_ver(self, user):
        """Host, participantes e admin podem ver a reunião/ata."""
        return (user.is_admin
                or self.criada_por == user.id
                or user.id in self.participante_ids())

    def __repr__(self):
        return f'<Reuniao {self.id} {self.titulo!r} ({self.status})>'


class ReuniaoParticipante(db.Model):
    __tablename__ = 'reuniao_participantes'

    reuniao_id = db.Column(
        db.Integer,
        db.ForeignKey('reunioes.id', ondelete='CASCADE'),
        primary_key=True
    )
    medico_id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)

    reuniao = db.relationship('Reuniao', back_populates='participantes')
    medico = db.relationship('User', foreign_keys=[medico_id])

    def __repr__(self):
        return f'<ReuniaoParticipante reuniao={self.reuniao_id} medico={self.medico_id}>'
