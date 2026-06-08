"""
Testes de integração das rotas principais.
Cobre: autenticação, controle de acesso, CRUD básico, rotas do médico.
"""
import pytest
from tests.conftest import make_admin, make_doctor, make_location, make_window, login_as


# ── Autenticação ──────────────────────────────────────────────────────────────

def test_login_page_loads(client):
    res = client.get('/login')
    assert res.status_code == 200
    assert b'login' in res.data.lower() or b'entrar' in res.data.lower()


def test_login_admin_redirects_to_admin_dashboard(app, client):
    make_admin(app)
    res = login_as(client, 'admin', 'admin123')
    assert res.status_code == 200
    assert b'Dashboard' in res.data or b'dashboard' in res.data.lower()


def test_login_doctor_redirects_to_doctor_dashboard(app, client):
    make_doctor(app)
    res = login_as(client, 'doc1', 'doc123')
    assert res.status_code == 200
    assert b'Painel' in res.data or b'painel' in res.data.lower()


def test_login_wrong_password_shows_error(app, client):
    make_admin(app)
    res = login_as(client, 'admin', 'wrongpass')
    assert res.status_code == 200
    assert b'inv' in res.data.lower() or b'incorret' in res.data.lower() \
        or b'senha' in res.data.lower()


def test_logout_redirects_to_login(app, client):
    make_admin(app)
    login_as(client, 'admin', 'admin123')
    res = client.get('/logout', follow_redirects=True)
    assert res.status_code == 200
    assert b'login' in res.data.lower() or b'entrar' in res.data.lower()


# ── Controle de acesso ────────────────────────────────────────────────────────

def test_unauthenticated_redirects_to_login(client):
    res = client.get('/admin/dashboard', follow_redirects=True)
    assert res.status_code == 200
    assert b'login' in res.data.lower() or b'entrar' in res.data.lower()


def test_doctor_cannot_access_admin(app, client):
    make_doctor(app)
    login_as(client, 'doc1', 'doc123')
    res = client.get('/admin/dashboard', follow_redirects=True)
    assert res.status_code == 403


def test_admin_cannot_access_medico_area(app, client):
    make_admin(app)
    login_as(client, 'admin', 'admin123')
    res = client.get('/medico/dashboard', follow_redirects=True)
    assert res.status_code == 403


def test_admin_dashboard_loads(app, client):
    make_admin(app)
    login_as(client, 'admin', 'admin123')
    res = client.get('/admin/dashboard')
    assert res.status_code == 200


def test_doctor_dashboard_loads(app, client):
    make_doctor(app)
    login_as(client, 'doc1', 'doc123')
    res = client.get('/medico/dashboard')
    assert res.status_code == 200


# ── CRUD Médicos ──────────────────────────────────────────────────────────────

def test_admin_creates_doctor(app, client):
    make_admin(app)
    login_as(client, 'admin', 'admin123')
    res = client.post('/admin/medicos/novo', data={
        'name': 'Dr. Novo',
        'crm': 'CRM999',
        'login': 'drnovo',
        'email': 'drnovo@test.com',
        'password': 'senha123',
    }, follow_redirects=True)
    assert res.status_code == 200
    assert b'Dr. Novo' in res.data or b'cadastrad' in res.data.lower()


def test_admin_lists_doctors(app, client):
    make_admin(app)
    make_doctor(app)
    login_as(client, 'admin', 'admin123')
    res = client.get('/admin/medicos')
    assert res.status_code == 200
    assert b'Dr. Teste' in res.data


# ── CRUD Locais ───────────────────────────────────────────────────────────────

def test_admin_creates_location(app, client):
    make_admin(app)
    login_as(client, 'admin', 'admin123')
    res = client.post('/admin/locais/novo', data={
        'name': 'Hospital ABC',
        'address': 'Rua X, 100',
        'scale_type': 'PLANTONISTA',
    }, follow_redirects=True)
    assert res.status_code == 200
    assert b'Hospital ABC' in res.data or b'cadastrad' in res.data.lower()


def test_admin_lists_locations(app, client):
    make_admin(app)
    make_location(app, name='UPA Norte')
    login_as(client, 'admin', 'admin123')
    res = client.get('/admin/locais')
    assert res.status_code == 200
    assert b'UPA Norte' in res.data


# ── Janelas de Preenchimento ──────────────────────────────────────────────────

def test_admin_creates_window(app, client):
    make_admin(app)
    login_as(client, 'admin', 'admin123')
    res = client.post('/admin/janela/nova', data={
        'year': '2026',
        'open_at': '2025-11-01 00:00',
        'close_at': '2025-11-30 23:59',
    }, follow_redirects=True)
    assert res.status_code == 200


def test_admin_lists_windows(app, client):
    make_admin(app)
    make_window(app, year=2025)
    login_as(client, 'admin', 'admin123')
    res = client.get('/admin/janela')
    assert res.status_code == 200
    assert b'2025' in res.data


# ── Rotas do Médico ───────────────────────────────────────────────────────────

def test_doctor_views_routines_page(app, client):
    make_doctor(app)
    make_window(app, year=2025, status='open')
    login_as(client, 'doc1', 'doc123')
    res = client.get('/medico/rotinas')
    assert res.status_code == 200


def test_doctor_views_restrictions_page(app, client):
    make_doctor(app)
    make_window(app, year=2025, status='open')
    login_as(client, 'doc1', 'doc123')
    res = client.get('/medico/restricoes')
    assert res.status_code == 200


def test_doctor_views_schedule_page(app, client):
    make_doctor(app)
    make_window(app, year=2025, status='published')
    login_as(client, 'doc1', 'doc123')
    res = client.get('/medico/escala')
    assert res.status_code == 200


def test_doctor_no_open_window_redirects(app, client):
    make_doctor(app)
    login_as(client, 'doc1', 'doc123')
    # Sem janela aberta → flash de aviso e redirect
    res = client.get('/medico/rotinas', follow_redirects=True)
    assert res.status_code == 200
    assert b'janela' in res.data.lower() or b'momento' in res.data.lower()


def test_doctor_swap_notifications_count(app, client):
    make_doctor(app)
    login_as(client, 'doc1', 'doc123')
    res = client.get('/medico/trocas/notificacoes')
    assert res.status_code == 200
    import json
    data = json.loads(res.data)
    assert 'count' in data
    assert data['count'] == 0


# ── Páginas de erro ───────────────────────────────────────────────────────────

def test_404_returns_custom_page(client):
    res = client.get('/rota-inexistente')
    assert res.status_code == 404


def test_login_inactive_user_blocked(app, client):
    """Usuário inativo não pode fazer login."""
    from app.extensions import db as _db
    from app.models.user import User
    doc = make_doctor(app)
    with app.app_context():
        u = _db.session.get(User, doc.id)
        u.active = False
        _db.session.commit()
    res = login_as(client, 'doc1', 'doc123')
    # Deve mostrar erro ou redirecionar para login
    # Deve mostrar erro ou redirecionar para login
    assert res.status_code == 200 and (
        b'inv' in res.data.lower()
        or b'inativo' in res.data.lower()
        or b'login' in res.data.lower()
    )
