"""
Testes unitários do scheduler.
Verifica: restrições, sem conflitos de data, distribuição igualitária,
expansão de rotinas (weekly/biweekly/monthly).
"""
import pytest
from datetime import date

from app.extensions import db
from app.models.schedule import DoctorRoutine, DoctorRestriction, Schedule
from app.services.scheduler import generate_schedule
from tests.conftest import make_doctor, make_location, make_link, make_window


def test_empty_links_returns_zero(app):
    """Sem vínculos → nenhum slot gerado."""
    w = make_window(app, year=2025)
    with app.app_context():
        result = generate_schedule(w.id)
    assert result['total_slots'] == 0
    assert result['routine_slots'] == 0
    assert result['generated_slots'] == 0


def test_restrictions_respected(app):
    """Médico com restrição em 01/01/2025 não deve ser escalado nessa data."""
    doc = make_doctor(app)
    loc = make_location(app)
    make_link(app, doc.id, loc.id, 'DIARISTA')
    w = make_window(app, year=2025)

    with app.app_context():
        db.session.add(DoctorRestriction(
            doctor_id=doc.id, window_id=w.id, restricted_date=date(2025, 1, 1),
        ))
        db.session.commit()

        generate_schedule(w.id)

        slot = Schedule.query.filter_by(window_id=w.id, date=date(2025, 1, 1)).first()
        # Com um único médico e restrição no dia, o slot deve estar descoberto
        assert slot is None


def test_no_date_conflicts(app):
    """Médico nunca escalonado duas vezes no mesmo dia."""
    doc = make_doctor(app)
    loc1 = make_location(app, name='UPA Norte', scale_type='DIARISTA')
    loc2 = make_location(app, name='UPA Sul', scale_type='DIARISTA')
    make_link(app, doc.id, loc1.id, 'DIARISTA')
    make_link(app, doc.id, loc2.id, 'DIARISTA')
    w = make_window(app, year=2025)

    with app.app_context():
        generate_schedule(w.id)
        schedules = Schedule.query.filter_by(window_id=w.id, doctor_id=doc.id).all()
        dates = [s.date for s in schedules]
        assert len(dates) == len(set(dates)), "Médico tem mais de um plantão no mesmo dia"


def test_equal_distribution_two_doctors(app):
    """Com dois médicos e uma localização, a carga deve ser quase igual."""
    doc1 = make_doctor(app, login='doc1', crm='C001')
    doc2 = make_doctor(app, login='doc2', crm='C002')
    loc = make_location(app)
    make_link(app, doc1.id, loc.id, 'DIARISTA')
    make_link(app, doc2.id, loc.id, 'DIARISTA')
    w = make_window(app, year=2025)

    with app.app_context():
        result = generate_schedule(w.id)
        # 2025 tem 365 dias; uma localização → 365 slots
        assert result['total_slots'] == 365
        assert result['uncovered_slots'] == []

        c1 = Schedule.query.filter_by(window_id=w.id, doctor_id=doc1.id).count()
        c2 = Schedule.query.filter_by(window_id=w.id, doctor_id=doc2.id).count()
        assert c1 + c2 == 365
        assert abs(c1 - c2) <= 1  # diferença máxima de 1 (365 é ímpar)


def test_weekly_routine_covers_all_mondays(app):
    """Rotina semanal na segunda deve cobrir todas as segundas de 2025."""
    doc = make_doctor(app)
    loc = make_location(app)
    make_link(app, doc.id, loc.id, 'DIARISTA')
    w = make_window(app, year=2025)

    with app.app_context():
        db.session.add(DoctorRoutine(
            doctor_id=doc.id, location_id=loc.id, window_id=w.id,
            frequency='weekly', day_of_week=0, scale_type='DIARISTA',
        ))
        db.session.commit()

        generate_schedule(w.id)

        routine_entries = (Schedule.query
                           .filter_by(window_id=w.id, doctor_id=doc.id, source='routine')
                           .all())
        for entry in routine_entries:
            assert entry.date.weekday() == 0, f"{entry.date} não é segunda-feira"

        # Contar segundas de 2025 (52 semanas + 1 dia extra = 53 segundas? Não, 2025 começa na quarta)
        mondays_2025 = sum(
            1 for n in range(365)
            if date.fromordinal(date(2025, 1, 1).toordinal() + n).weekday() == 0
        )
        assert len(routine_entries) == mondays_2025


def test_biweekly_routine_only_specific_week(app):
    """Rotina quinzenal na 1ª semana deve cobrir apenas as quartas da 1ª semana."""
    doc = make_doctor(app)
    loc = make_location(app)
    make_link(app, doc.id, loc.id, 'DIARISTA')
    w = make_window(app, year=2025)

    with app.app_context():
        db.session.add(DoctorRoutine(
            doctor_id=doc.id, location_id=loc.id, window_id=w.id,
            frequency='biweekly', day_of_week=2, week_of_month=1,
            scale_type='DIARISTA',
        ))
        db.session.commit()

        generate_schedule(w.id)

        entries = (Schedule.query
                   .filter_by(window_id=w.id, doctor_id=doc.id, source='routine')
                   .all())
        for entry in entries:
            assert entry.date.weekday() == 2, f"{entry.date} não é quarta"
            assert (entry.date.day - 1) // 7 + 1 == 1, f"{entry.date} não é 1ª semana"


def test_uncovered_slot_when_all_restricted(app):
    """Se todos os médicos têm restrição em uma data, o slot fica descoberto."""
    doc1 = make_doctor(app, login='doc1', crm='C001')
    doc2 = make_doctor(app, login='doc2', crm='C002')
    loc = make_location(app)
    make_link(app, doc1.id, loc.id, 'DIARISTA')
    make_link(app, doc2.id, loc.id, 'DIARISTA')
    w = make_window(app, year=2025)
    target = date(2025, 6, 15)

    with app.app_context():
        for doc_id in [doc1.id, doc2.id]:
            db.session.add(DoctorRestriction(
                doctor_id=doc_id, window_id=w.id, restricted_date=target
            ))
        db.session.commit()

        result = generate_schedule(w.id)

        uncovered_dates = [u['date'] for u in result['uncovered_slots']]
        assert target in uncovered_dates


def test_routine_takes_priority_over_generation(app):
    """Slot coberto por rotina deve ter source='routine', não 'generated'."""
    doc = make_doctor(app)
    loc = make_location(app)
    make_link(app, doc.id, loc.id, 'DIARISTA')
    w = make_window(app, year=2025)

    with app.app_context():
        db.session.add(DoctorRoutine(
            doctor_id=doc.id, location_id=loc.id, window_id=w.id,
            frequency='weekly', day_of_week=0, scale_type='DIARISTA',
        ))
        db.session.commit()

        generate_schedule(w.id)

        # Primeira segunda de 2025: 6 de janeiro
        monday = date(2025, 1, 6)
        entry = Schedule.query.filter_by(
            window_id=w.id, date=monday, location_id=loc.id
        ).first()
        assert entry is not None
        assert entry.source == 'routine'
        assert entry.doctor_id == doc.id
