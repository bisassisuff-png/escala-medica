"""
Testes do kpi_service: doctor_totals, avg_load, overloaded/underloaded.
"""
from datetime import date

from app.extensions import db
from app.models.location import LocationScaleRequirement, get_required_loc_keys
from app.models.schedule import Schedule
from app.services.kpi_service import get_coverage_summary, get_dashboard_data, get_doctor_month_stats
from tests.conftest import make_doctor, make_link, make_location, make_window


def _add_schedule(app, window_id, doctor_id, location_id, day, scale_type='DIARISTA'):
    with app.app_context():
        s = Schedule(
            window_id=window_id, date=day,
            location_id=location_id, scale_type=scale_type,
            doctor_id=doctor_id, source='generated', status='published',
        )
        db.session.add(s)
        db.session.commit()


def test_doctor_totals_correct(app):
    """doctor_totals deve contar corretamente os plantões por médico no mês."""
    doc1 = make_doctor(app, login='doc1', crm='C001')
    doc2 = make_doctor(app, login='doc2', crm='C002')
    loc = make_location(app)
    w = make_window(app, year=2025, status='published')

    for day in [1, 5, 10]:
        _add_schedule(app, w.id, doc1.id, loc.id, date(2025, 1, day))
    _add_schedule(app, w.id, doc2.id, loc.id, date(2025, 1, 15))

    with app.app_context():
        data = get_dashboard_data(w.id, month=1)
        assert data['doctor_totals'].get(doc1.id) == 3
        assert data['doctor_totals'].get(doc2.id) == 1


def test_avg_load_calculation(app):
    """avg_load = média de plantões por médico no mês."""
    doc1 = make_doctor(app, login='doc1', crm='C001')
    doc2 = make_doctor(app, login='doc2', crm='C002')
    loc = make_location(app)
    w = make_window(app, year=2025, status='published')

    for day in [1, 5, 10, 15]:
        _add_schedule(app, w.id, doc1.id, loc.id, date(2025, 1, day))
    for day in [2, 8]:
        _add_schedule(app, w.id, doc2.id, loc.id, date(2025, 1, day))

    with app.app_context():
        data = get_dashboard_data(w.id, month=1)
        assert data['avg_load'] == 3.0  # (4+2)/2


def test_overloaded_identified(app):
    """Médico com >130% da média deve aparecer em overloaded."""
    doc1 = make_doctor(app, login='doc1', crm='C001')
    doc2 = make_doctor(app, login='doc2', crm='C002')
    loc = make_location(app)
    w = make_window(app, year=2025, status='published')

    for day in range(1, 11):  # doc1: 10 plantões
        _add_schedule(app, w.id, doc1.id, loc.id, date(2025, 1, day))
    for day in [15, 20]:  # doc2: 2 plantões
        _add_schedule(app, w.id, doc2.id, loc.id, date(2025, 1, day))
    # avg=6, 130%=7.8 → doc1(10) está sobrecarregado

    with app.app_context():
        data = get_dashboard_data(w.id, month=1)
        assert doc1.id in data['overloaded']
        assert doc2.id not in data['overloaded']


def test_underloaded_identified(app):
    """Médico com <70% da média deve aparecer em underloaded."""
    doc1 = make_doctor(app, login='doc1', crm='C001')
    doc2 = make_doctor(app, login='doc2', crm='C002')
    loc = make_location(app)
    w = make_window(app, year=2025, status='published')

    for day in range(1, 11):  # doc1: 10 plantões
        _add_schedule(app, w.id, doc1.id, loc.id, date(2025, 1, day))
    for day in [15, 20]:  # doc2: 2 plantões
        _add_schedule(app, w.id, doc2.id, loc.id, date(2025, 1, day))
    # avg=6, 70%=4.2 → doc2(2) está subutilizado

    with app.app_context():
        data = get_dashboard_data(w.id, month=1)
        assert doc2.id in data['underloaded']
        assert doc1.id not in data['underloaded']


def test_get_doctor_month_stats_total(app):
    """get_doctor_month_stats deve contar apenas os plantões do médico no mês."""
    doc = make_doctor(app)
    loc = make_location(app)
    w = make_window(app, year=2025, status='published')

    for day in [1, 3, 5, 7]:
        _add_schedule(app, w.id, doc.id, loc.id, date(2025, 3, day))
    _add_schedule(app, w.id, doc.id, loc.id, date(2025, 4, 1))  # fora do mês

    with app.app_context():
        stats = get_doctor_month_stats(doc.id, w.id, month=3)
        assert stats['total'] == 4


def test_dashboard_data_empty_window(app):
    """Window inexistente deve retornar dict vazio."""
    with app.app_context():
        data = get_dashboard_data(9999, month=1)
        assert data == {}


def test_get_required_loc_keys_default_all_required(app):
    """Sem registros em LocationScaleRequirement, todos os pares (local, tipo) ativos são obrigatórios."""
    doc = make_doctor(app)
    loc = make_location(app, name='CIAS')
    make_link(app, doc.id, loc.id, scale_type='P1')
    make_link(app, doc.id, loc.id, scale_type='P2')

    with app.app_context():
        keys = get_required_loc_keys()
        assert (loc.id, 'P1') in keys
        assert (loc.id, 'P2') in keys


def test_get_required_loc_keys_excludes_optional(app):
    """Um registro required=False remove o par (local, tipo) do conjunto de obrigatórios."""
    doc = make_doctor(app)
    loc = make_location(app, name='CIAS')
    make_link(app, doc.id, loc.id, scale_type='P1')
    make_link(app, doc.id, loc.id, scale_type='P2')

    with app.app_context():
        db.session.add(LocationScaleRequirement(location_id=loc.id, scale_type='P2', required=False))
        db.session.commit()

        keys = get_required_loc_keys()
        assert (loc.id, 'P1') in keys
        assert (loc.id, 'P2') not in keys


def test_coverage_summary_excludes_optional_scale_type(app):
    """get_coverage_summary não conta pares (local, tipo) marcados como opcionais."""
    doc = make_doctor(app)
    loc = make_location(app, name='CIAS')
    make_link(app, doc.id, loc.id, scale_type='P1')
    make_link(app, doc.id, loc.id, scale_type='P2')
    w = make_window(app, year=2025, status='published')

    with app.app_context():
        total_before = get_coverage_summary(w.id, month=1)['total']

        db.session.add(LocationScaleRequirement(location_id=loc.id, scale_type='P2', required=False))
        db.session.commit()

        total_after = get_coverage_summary(w.id, month=1)['total']
        assert total_after == total_before // 2


def test_weekday_counts(app):
    """weekday_counts deve contar plantões por dia da semana corretamente."""
    doc = make_doctor(app)
    loc = make_location(app)
    w = make_window(app, year=2025, status='published')

    # 2025-01-06 é segunda (weekday=0); 2025-01-07 é terça (weekday=1)
    _add_schedule(app, w.id, doc.id, loc.id, date(2025, 1, 6))
    _add_schedule(app, w.id, doc.id, loc.id, date(2025, 1, 7))

    with app.app_context():
        data = get_dashboard_data(w.id, month=1)
        assert data['weekday_counts'].get(0, 0) == 1  # segunda
        assert data['weekday_counts'].get(1, 0) == 1  # terça
