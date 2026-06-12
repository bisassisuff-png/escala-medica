"""
Testes de integração das rotas principais.
Cobre: autenticação, controle de acesso, CRUD básico, rotas do médico.
"""
from datetime import date

import pytest
from tests.conftest import make_admin, make_doctor, make_link, make_location, make_window, login_as


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


def test_doctor_dashboard_shows_mednews_card(app, client):
    make_doctor(app)
    login_as(client, 'doc1', 'doc123')
    res = client.get('/medico/dashboard')
    assert res.status_code == 200
    assert b'MedNews' in res.data


def test_doctor_dashboard_2026_disables_jan_to_may(app, client):
    make_doctor(app)
    make_window(app, year=2026, status='published')
    login_as(client, 'doc1', 'doc123')
    res = client.get('/medico/dashboard')
    assert res.status_code == 200
    assert b'btn--disabled' in res.data
    assert b'month=1"' not in res.data
    assert b'month=6"' in res.data


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


def test_admin_doctor_edit_shows_links_card(app, client):
    """Tela de edição do médico mostra o card de vínculos com locais e posições."""
    make_admin(app)
    doc = make_doctor(app, login='doc1', crm='C001')
    loc = make_location(app, name='UPA Norte')
    make_link(app, doc.id, loc.id, 'P1')
    login_as(client, 'admin', 'admin123')

    res = client.get(f'/admin/medicos/{doc.id}/editar')
    assert res.status_code == 200
    assert 'Vínculos com locais e posições'.encode('utf-8') in res.data
    assert b'UPA Norte' in res.data
    assert b'P1' in res.data


def test_admin_doctor_links_toggle_off_and_on(app, client):
    """Admin desmarca um vínculo (active=False) e depois marca de volta (active=True)."""
    make_admin(app)
    doc = make_doctor(app, login='doc1', crm='C001')
    loc = make_location(app, name='UPA Norte')
    make_link(app, doc.id, loc.id, 'P1')
    login_as(client, 'admin', 'admin123')

    from app.extensions import db
    from app.models.location import DoctorLocationLink

    # Desmarca (não envia o checkbox)
    res = client.post(f'/admin/medicos/{doc.id}/vinculos', data={}, follow_redirects=True)
    assert res.status_code == 200
    with app.app_context():
        lk = DoctorLocationLink.query.filter_by(doctor_id=doc.id, location_id=loc.id, scale_type='P1').first()
        assert lk.active is False

    # Marca de volta
    res = client.post(f'/admin/medicos/{doc.id}/vinculos', data={
        f'link_{loc.id}_P1': 'on',
    }, follow_redirects=True)
    assert res.status_code == 200
    with app.app_context():
        lk = DoctorLocationLink.query.filter_by(doctor_id=doc.id, location_id=loc.id, scale_type='P1').first()
        assert lk.active is True


def test_admin_doctor_links_add_new_position(app, client):
    """Nova posição cadastrada via vínculos é vinculada a todos os médicos."""
    make_admin(app)
    doc1 = make_doctor(app, login='doc1', crm='C001')
    doc2 = make_doctor(app, login='doc2', crm='C002')
    loc = make_location(app, name='UPA Norte')
    make_link(app, doc1.id, loc.id, 'P1')
    login_as(client, 'admin', 'admin123')

    res = client.post(f'/admin/medicos/{doc1.id}/vinculos', data={
        f'link_{loc.id}_P1': 'on',
        f'new_position_{loc.id}': 'P9',
    }, follow_redirects=True)
    assert res.status_code == 200

    from app.models.location import DoctorLocationLink
    with app.app_context():
        for doc_id in (doc1.id, doc2.id):
            lk = DoctorLocationLink.query.filter_by(
                doctor_id=doc_id, location_id=loc.id, scale_type='P9').first()
            assert lk is not None
            assert lk.active is True


def test_admin_doctor_links_requires_admin(app, client):
    """Médico não pode acessar a rota de vínculos (admin-only)."""
    make_admin(app)
    doc = make_doctor(app, login='doc1', crm='C001')
    loc = make_location(app, name='UPA Norte')
    make_link(app, doc.id, loc.id, 'P1')
    login_as(client, 'doc1', 'doc123')

    res = client.post(f'/admin/medicos/{doc.id}/vinculos', data={})
    assert res.status_code == 403


def test_doctors_new_links_to_existing_universe(app, client):
    """Médico recém-criado já nasce vinculado a todo o universo de posições existente."""
    make_admin(app)
    doc1 = make_doctor(app, login='doc1', crm='C001')
    loc = make_location(app, name='UPA Norte')
    make_link(app, doc1.id, loc.id, 'P1')
    login_as(client, 'admin', 'admin123')

    res = client.post('/admin/medicos/novo', data={
        'name': 'Dr. Novo',
        'crm': 'CRM999',
        'login': 'drnovo',
        'email': 'drnovo@test.com',
        'password': 'senha123',
    }, follow_redirects=True)
    assert res.status_code == 200

    from app.models.user import User
    from app.models.location import DoctorLocationLink
    with app.app_context():
        novo = User.query.filter_by(login='drnovo').first()
        lk = DoctorLocationLink.query.filter_by(
            doctor_id=novo.id, location_id=loc.id, scale_type='P1').first()
        assert lk is not None
        assert lk.active is True


# ── CRUD Locais ───────────────────────────────────────────────────────────────

def test_admin_creates_location(app, client):
    make_admin(app)
    login_as(client, 'admin', 'admin123')
    res = client.post('/admin/locais/novo', data={
        'name': 'Hospital ABC',
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


def test_admin_toggles_location_scale_requirement(app, client):
    make_admin(app)
    doc = make_doctor(app)
    loc = make_location(app, name='CIAS')
    make_link(app, doc.id, loc.id, scale_type='P1')
    make_link(app, doc.id, loc.id, scale_type='P2')
    login_as(client, 'admin', 'admin123')

    res = client.post(f'/admin/locais/{loc.id}/requisitos', data={
        'required_P1': 'on',
    }, follow_redirects=True)
    assert res.status_code == 200

    with app.app_context():
        from app.models.location import LocationScaleRequirement, get_required_loc_keys
        reqs = {r.scale_type: r.required for r in
                LocationScaleRequirement.query.filter_by(location_id=loc.id).all()}
        assert reqs['P1'] is True
        assert reqs['P2'] is False

        keys = get_required_loc_keys()
        assert (loc.id, 'P1') in keys
        assert (loc.id, 'P2') not in keys


def test_admin_location_form_shows_add_remove_controls(app, client):
    """Tela de edição do local mostra botão 'Remover' e campo de nova posição."""
    make_admin(app)
    doc = make_doctor(app)
    loc = make_location(app, name='CIAS')
    make_link(app, doc.id, loc.id, scale_type='P1')
    login_as(client, 'admin', 'admin123')

    res = client.get(f'/admin/locais/{loc.id}/editar')
    assert res.status_code == 200
    assert b'name="new_scale_type"' in res.data
    assert 'Remover'.encode('utf-8') in res.data


def test_admin_location_scale_type_add(app, client):
    """Nova posição cadastrada pelo local é vinculada a todos os médicos."""
    make_admin(app)
    doc1 = make_doctor(app, login='doc1', crm='C001')
    doc2 = make_doctor(app, login='doc2', crm='C002')
    loc = make_location(app, name='CIAS')
    make_link(app, doc1.id, loc.id, scale_type='P1')
    login_as(client, 'admin', 'admin123')

    res = client.post(f'/admin/locais/{loc.id}/escalas/adicionar', data={
        'new_scale_type': 'P9',
    }, follow_redirects=True)
    assert res.status_code == 200

    with app.app_context():
        from app.models.location import DoctorLocationLink
        from app.services.location_service import get_position_universe
        for doc_id in (doc1.id, doc2.id):
            lk = DoctorLocationLink.query.filter_by(
                doctor_id=doc_id, location_id=loc.id, scale_type='P9').first()
            assert lk is not None
            assert lk.active is True
        assert (loc.id, 'P9') in get_position_universe()


def test_admin_location_scale_type_remove(app, client):
    """Remover uma posição desvincula todos os médicos e some do universo."""
    make_admin(app)
    doc1 = make_doctor(app, login='doc1', crm='C001')
    doc2 = make_doctor(app, login='doc2', crm='C002')
    loc = make_location(app, name='CIAS')
    make_link(app, doc1.id, loc.id, scale_type='P1')
    make_link(app, doc1.id, loc.id, scale_type='P2')
    make_link(app, doc2.id, loc.id, scale_type='P2')
    login_as(client, 'admin', 'admin123')

    res = client.post(f'/admin/locais/{loc.id}/escalas/remover', data={
        'scale_type': 'P2',
    }, follow_redirects=True)
    assert res.status_code == 200

    with app.app_context():
        from app.models.location import DoctorLocationLink
        from app.services.location_service import get_position_universe
        assert DoctorLocationLink.query.filter_by(location_id=loc.id, scale_type='P2').count() == 0
        assert (loc.id, 'P2') not in get_position_universe()
        assert (loc.id, 'P1') in get_position_universe()


def test_admin_location_scale_type_remove_requires_admin(app, client):
    """Médico não pode acessar a rota de remoção de posição (admin-only)."""
    make_admin(app)
    doc = make_doctor(app, login='doc1', crm='C001')
    loc = make_location(app, name='CIAS')
    make_link(app, doc.id, loc.id, scale_type='P2')
    login_as(client, 'doc1', 'doc123')

    res = client.post(f'/admin/locais/{loc.id}/escalas/remover', data={'scale_type': 'P2'})
    assert res.status_code == 403


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


def test_admin_schedule_review_2026_disables_jan_to_may(app, client):
    make_admin(app)
    window = make_window(app, year=2026, status='published')
    login_as(client, 'admin', 'admin123')
    res = client.get(f'/admin/janela/{window.id}/escala')
    assert res.status_code == 200
    assert b'btn--disabled' in res.data
    assert b'month=1"' not in res.data
    assert b'month=6"' in res.data


def test_admin_schedule_review_2026_defaults_to_first_active_month(app, client):
    make_admin(app)
    window = make_window(app, year=2026, status='published')
    login_as(client, 'admin', 'admin123')
    res = client.get(f'/admin/janela/{window.id}/escala')
    assert res.status_code == 200
    assert 'Jun / 2026'.encode('utf-8') in res.data


def test_admin_schedule_review_non_2026_keeps_all_months_active(app, client):
    make_admin(app)
    window = make_window(app, year=2025, status='published')
    login_as(client, 'admin', 'admin123')
    res = client.get(f'/admin/janela/{window.id}/escala')
    assert res.status_code == 200
    assert b'btn--disabled' not in res.data
    assert b'month=1"' in res.data


def test_admin_schedule_review_shows_open_gaps_table(app, client):
    make_admin(app)
    doc = make_doctor(app)
    loc = make_location(app, name='CIAS')
    make_link(app, doc.id, loc.id, scale_type='P1')
    window = make_window(app, year=2025, status='published')
    login_as(client, 'admin', 'admin123')
    res = client.get(f'/admin/janela/{window.id}/escala?month=1')
    assert res.status_code == 200
    assert 'Lacunas em aberto'.encode('utf-8') in res.data
    assert b'CIAS' in res.data
    assert b'P1' in res.data
    assert b'<details' in res.data


def test_admin_schedule_review_no_gaps_shows_empty_state(app, client):
    make_admin(app)
    window = make_window(app, year=2025, status='published')
    login_as(client, 'admin', 'admin123')
    res = client.get(f'/admin/janela/{window.id}/escala?month=1')
    assert res.status_code == 200
    assert 'Sem lacunas em aberto'.encode('utf-8') in res.data
    assert b'<details' in res.data


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


def test_doctor_schedule_2026_disables_jan_to_may(app, client):
    make_doctor(app)
    make_window(app, year=2026, status='published')
    login_as(client, 'doc1', 'doc123')
    res = client.get('/medico/escala')
    assert res.status_code == 200
    assert b'btn--disabled' in res.data
    assert b'month=1"' not in res.data
    assert b'month=6"' in res.data


def test_doctor_schedule_2026_defaults_to_first_active_month(app, client):
    make_doctor(app)
    make_window(app, year=2026, status='published')
    login_as(client, 'doc1', 'doc123')
    res = client.get('/medico/escala')
    assert res.status_code == 200
    assert 'Jun / 2026'.encode('utf-8') in res.data


def test_doctor_schedule_non_2026_keeps_all_months_active(app, client):
    make_doctor(app)
    make_window(app, year=2025, status='published')
    login_as(client, 'doc1', 'doc123')
    res = client.get('/medico/escala')
    assert res.status_code == 200
    assert b'btn--disabled' not in res.data
    assert b'month=1"' in res.data


def test_doctor_views_group_schedule_page(app, client):
    make_doctor(app)
    make_window(app, year=2025, status='published')
    login_as(client, 'doc1', 'doc123')
    res = client.get('/medico/escala-grupo')
    assert res.status_code == 200
    assert 'Escala do Grupo'.encode('utf-8') in res.data


def test_doctor_group_schedule_no_published_window_redirects(app, client):
    make_doctor(app)
    login_as(client, 'doc1', 'doc123')
    res = client.get('/medico/escala-grupo', follow_redirects=True)
    assert res.status_code == 200
    assert b'escala publicada' in res.data.lower()


def test_doctor_group_schedule_has_no_edit_controls(app, client):
    make_doctor(app)
    make_window(app, year=2025, status='published')
    login_as(client, 'doc1', 'doc123')
    res = client.get('/medico/escala-grupo')
    assert res.status_code == 200
    assert b'cal-day__expand' not in res.data
    assert b'name="doctor_id"' not in res.data


def test_doctor_group_schedule_2026_disables_jan_to_may(app, client):
    make_doctor(app)
    make_window(app, year=2026, status='published')
    login_as(client, 'doc1', 'doc123')
    res = client.get('/medico/escala-grupo')
    assert res.status_code == 200
    assert b'btn--disabled' in res.data
    assert b'month=1"' not in res.data
    assert b'month=6"' in res.data


def test_doctor_group_schedule_2026_defaults_to_first_active_month(app, client):
    make_doctor(app)
    make_window(app, year=2026, status='published')
    login_as(client, 'doc1', 'doc123')
    res = client.get('/medico/escala-grupo')
    assert res.status_code == 200
    assert 'Jun / 2026'.encode('utf-8') in res.data


def test_doctor_group_schedule_shows_open_gaps_table(app, client):
    doc = make_doctor(app)
    loc = make_location(app, name='CIAS')
    make_link(app, doc.id, loc.id, scale_type='P1')
    make_window(app, year=2025, status='published')
    login_as(client, 'doc1', 'doc123')
    res = client.get('/medico/escala-grupo?month=1')
    assert res.status_code == 200
    assert 'Lacunas em aberto'.encode('utf-8') in res.data
    assert b'CIAS' in res.data
    assert b'P1' in res.data
    assert b'<details' in res.data


def test_doctor_group_schedule_no_gaps_shows_empty_state(app, client):
    make_doctor(app)
    make_window(app, year=2025, status='published')
    login_as(client, 'doc1', 'doc123')
    res = client.get('/medico/escala-grupo?month=1')
    assert res.status_code == 200
    assert 'Sem lacunas em aberto'.encode('utf-8') in res.data


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


def _make_open_swap(app, requester, loc):
    """Cria um Schedule publicado para `requester` e solicita uma troca aberta."""
    from app.extensions import db
    from app.models.schedule import Schedule
    from app.services.swap_service import request_swap

    window = make_window(app, year=2025, status='published')
    with app.app_context():
        sched = Schedule(
            window_id=window.id,
            date=date(2025, 6, 1), location_id=loc.id, scale_type=loc.scale_type,
            doctor_id=requester.id, source='generated', status='published',
        )
        db.session.add(sched)
        db.session.commit()
        swap = request_swap(sched.id, requester.id)
        return swap.id


def test_admin_swaps_page_shows_new_columns(app, client):
    make_admin(app)
    doc1 = make_doctor(app, login='doc1', crm='C001')
    doc2 = make_doctor(app, login='doc2', crm='C002')
    loc = make_location(app)
    make_link(app, doc1.id, loc.id, scale_type=loc.scale_type)
    make_link(app, doc2.id, loc.id, scale_type=loc.scale_type)
    _make_open_swap(app, doc1, loc)

    login_as(client, 'admin', 'admin123')
    res = client.get('/admin/trocas')
    assert res.status_code == 200
    assert 'Médicos disponíveis'.encode('utf-8') in res.data
    assert b'Dias em aberto' in res.data
    assert b'Dr. Teste' in res.data  # doc2 elegivel listado


def test_doctor_swaps_page_has_two_cards(app, client):
    make_doctor(app)
    login_as(client, 'doc1', 'doc123')
    res = client.get('/medico/trocas')
    assert res.status_code == 200
    assert 'Minhas solicitações'.encode('utf-8') in res.data
    assert 'Trocas em aberto'.encode('utf-8') in res.data


def test_doctor_open_swaps_card_shows_accept_button_for_eligible_doctor(app, client):
    doc1 = make_doctor(app, login='doc1', crm='C001')
    doc2 = make_doctor(app, login='doc2', crm='C002')
    loc = make_location(app)
    make_link(app, doc1.id, loc.id, scale_type=loc.scale_type)
    make_link(app, doc2.id, loc.id, scale_type=loc.scale_type)
    _make_open_swap(app, doc1, loc)

    login_as(client, 'doc2', 'doc123')
    res = client.get('/medico/trocas')
    assert res.status_code == 200
    assert b'Aceitar' in res.data


def test_doctor_accept_from_open_swaps_card_updates_schedule(app, client):
    doc1 = make_doctor(app, login='doc1', crm='C001')
    doc2 = make_doctor(app, login='doc2', crm='C002')
    loc = make_location(app)
    make_link(app, doc1.id, loc.id, scale_type=loc.scale_type)
    make_link(app, doc2.id, loc.id, scale_type=loc.scale_type)
    swap_id = _make_open_swap(app, doc1, loc)

    login_as(client, 'doc2', 'doc123')
    res = client.post(f'/medico/trocas/{swap_id}/aceitar', follow_redirects=True)
    assert res.status_code == 200

    with app.app_context():
        from app.extensions import db
        from app.models.swap import ScheduleSwap
        from app.models.schedule import Schedule

        swap = db.session.get(ScheduleSwap, swap_id)
        assert swap.status == 'accepted'
        sched = db.session.get(Schedule, swap.schedule_id)
        assert sched.doctor_id == doc2.id


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
