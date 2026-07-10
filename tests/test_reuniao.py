"""Testes do módulo de reuniões — foco em autorização (host-only / participantes)."""
import io

from app.extensions import db as _db
from app.models.reuniao import Reuniao, ReuniaoParticipante

from tests.conftest import make_admin, make_doctor, login_as


def _criar_reuniao(app, criada_por, participantes=(), status='aberta', titulo='Reunião X'):
    with app.app_context():
        r = Reuniao(titulo=titulo, criada_por=criada_por, status=status)
        _db.session.add(r)
        _db.session.flush()
        for pid in participantes:
            _db.session.add(ReuniaoParticipante(reuniao_id=r.id, medico_id=pid))
        _db.session.commit()
        return r.id


def test_admin_cria_reuniao(app, client):
    admin = make_admin(app)
    doc = make_doctor(app)
    login_as(client, admin.login, 'admin123')

    resp = client.post('/reuniao/criar',
                       data={'titulo': 'Reunião de escala', 'participantes': [str(doc.id)]},
                       follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        r = Reuniao.query.filter_by(titulo='Reunião de escala').first()
        assert r is not None
        assert r.criada_por == admin.id
        assert doc.id in r.participante_ids()


def test_medico_nao_cria_reuniao(app, client):
    doc = make_doctor(app)
    login_as(client, doc.login, 'doc123')
    resp = client.get('/reuniao/criar')
    assert resp.status_code == 403


def test_somente_host_envia_chunk(app, client):
    admin = make_admin(app)
    doc = make_doctor(app)
    rid = _criar_reuniao(app, criada_por=admin.id, participantes=[doc.id], status='gravando')

    # participante não-host → 403
    login_as(client, doc.login, 'doc123')
    resp = client.post('/reuniao/chunk',
                       data={'reuniao_id': str(rid), 'seq': '0',
                             'chunk': (io.BytesIO(b'\x1aE\xdf\xa3fake'), 'c.webm')},
                       content_type='multipart/form-data')
    assert resp.status_code == 403

    # host (admin criador) → 200
    client.get('/logout')
    login_as(client, admin.login, 'admin123')
    resp = client.post('/reuniao/chunk',
                       data={'reuniao_id': str(rid), 'seq': '0',
                             'chunk': (io.BytesIO(b'\x1aE\xdf\xa3fake'), 'c.webm')},
                       content_type='multipart/form-data')
    assert resp.status_code == 200
    assert resp.get_json()['ok'] is True


def test_ata_visivel_so_para_participantes(app, client):
    admin = make_admin(app)
    participante = make_doctor(app, login='doc_in', crm='CRMIN')
    estranho = make_doctor(app, login='doc_out', crm='CRMOUT')
    rid = _criar_reuniao(app, criada_por=admin.id, participantes=[participante.id],
                         status='concluida')
    with app.app_context():
        r = _db.session.get(Reuniao, rid)
        r.ata = '## Data\n10/07/2026'
        _db.session.commit()

    # não-participante → 403
    login_as(client, estranho.login, 'doc123')
    assert client.get(f'/reuniao/{rid}/ata').status_code == 403

    # participante → 200
    client.get('/logout')
    login_as(client, participante.login, 'doc123')
    resp = client.get(f'/reuniao/{rid}/ata')
    assert resp.status_code == 200
    assert 'Data' in resp.get_data(as_text=True)


def test_modulo_desativado_bloqueia(app, client):
    """Com REUNIOES_ENABLED=False, todas as rotas mostram a página 'em breve'."""
    admin = make_admin(app)
    rid = _criar_reuniao(app, criada_por=admin.id)
    login_as(client, admin.login, 'admin123')

    app.config['REUNIOES_ENABLED'] = False
    try:
        resp = client.get('/reuniao/')
        assert resp.status_code == 200
        assert 'em breve' in resp.get_data(as_text=True).lower()

        # ação (criar) também é bloqueada e NÃO executa
        resp = client.post('/reuniao/criar',
                           data={'titulo': 'Não deve criar', 'participantes': []})
        assert 'em breve' in resp.get_data(as_text=True).lower()
        with app.app_context():
            assert Reuniao.query.filter_by(titulo='Não deve criar').first() is None
    finally:
        app.config['REUNIOES_ENABLED'] = True


def test_entrar_sem_livekit_retorna_503(app, client):
    admin = make_admin(app)
    rid = _criar_reuniao(app, criada_por=admin.id)
    login_as(client, admin.login, 'admin123')

    # Força o cenário "LiveKit não configurado" (independe do .env ambiente).
    saved = {k: app.config.get(k) for k in
             ('LIVEKIT_API_KEY', 'LIVEKIT_API_SECRET', 'LIVEKIT_WS_URL')}
    for k in saved:
        app.config[k] = None
    try:
        resp = client.post('/reuniao/entrar', data={'reuniao_id': str(rid)})
        assert resp.status_code == 503
    finally:
        app.config.update(saved)
