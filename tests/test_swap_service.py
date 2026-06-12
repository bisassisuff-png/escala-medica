"""
Testes unitários do swap_service.
Verifica: criação de swap, notificações, elegibilidade, aceite, cancelamento.
"""
import pytest
from datetime import date

from app.extensions import db
from app.models.schedule import Schedule, DoctorRestriction
from app.models.swap import ScheduleSwap, SwapNotification
from app.services.swap_service import (
    request_swap, accept_swap, cancel_swap, admin_force_swap, build_swap_view_data,
)
from tests.conftest import make_doctor, make_location, make_link, make_window


def _make_schedule(app, doctor_id, location_id, window_id,
                   scale_type='DIARISTA', day=date(2025, 6, 1),
                   status='published'):
    with app.app_context():
        s = Schedule(
            window_id=window_id, date=day,
            location_id=location_id, scale_type=scale_type,
            doctor_id=doctor_id, source='generated', status=status,
        )
        db.session.add(s)
        db.session.commit()
        return s.id


def test_request_swap_creates_swap_and_notifies(app):
    """Solicitação de troca deve criar swap e notificar médicos elegíveis."""
    doc1 = make_doctor(app, login='doc1', crm='C001')
    doc2 = make_doctor(app, login='doc2', crm='C002')
    loc = make_location(app)
    make_link(app, doc1.id, loc.id, 'DIARISTA')
    make_link(app, doc2.id, loc.id, 'DIARISTA')
    w = make_window(app, year=2025)
    sched_id = _make_schedule(app, doc1.id, loc.id, w.id)

    with app.app_context():
        swap = request_swap(sched_id, doc1.id)
        assert swap.status == 'open'
        assert swap.requester_id == doc1.id

        notifs = SwapNotification.query.filter_by(swap_id=swap.id).all()
        notified_ids = {n.notified_doctor_id for n in notifs}
        assert doc2.id in notified_ids
        assert doc1.id not in notified_ids  # solicitante não notificado


def test_request_swap_restricted_doctor_not_notified(app):
    """Médico com restrição na data não deve ser notificado."""
    doc1 = make_doctor(app, login='doc1', crm='C001')
    doc2 = make_doctor(app, login='doc2', crm='C002')
    loc = make_location(app)
    make_link(app, doc1.id, loc.id, 'DIARISTA')
    make_link(app, doc2.id, loc.id, 'DIARISTA')
    w = make_window(app, year=2025)
    target = date(2025, 6, 1)
    sched_id = _make_schedule(app, doc1.id, loc.id, w.id, day=target)

    with app.app_context():
        db.session.add(DoctorRestriction(
            doctor_id=doc2.id, window_id=w.id, restricted_date=target
        ))
        db.session.commit()

        swap = request_swap(sched_id, doc1.id)
        notifs = SwapNotification.query.filter_by(swap_id=swap.id).all()
        notified_ids = {n.notified_doctor_id for n in notifs}
        assert doc2.id not in notified_ids


def test_request_swap_busy_doctor_not_notified(app):
    """Médico já escalado no dia não deve ser notificado para a troca."""
    doc1 = make_doctor(app, login='doc1', crm='C001')
    doc2 = make_doctor(app, login='doc2', crm='C002')
    loc1 = make_location(app, name='UPA Norte', scale_type='DIARISTA')
    loc2 = make_location(app, name='UPA Sul', scale_type='DIARISTA')
    make_link(app, doc1.id, loc1.id, 'DIARISTA')
    make_link(app, doc2.id, loc1.id, 'DIARISTA')
    make_link(app, doc2.id, loc2.id, 'DIARISTA')
    w = make_window(app, year=2025)
    target = date(2025, 6, 1)

    sched1_id = _make_schedule(app, doc1.id, loc1.id, w.id, day=target)
    _make_schedule(app, doc2.id, loc2.id, w.id, day=target)

    with app.app_context():
        swap = request_swap(sched1_id, doc1.id)
        notifs = SwapNotification.query.filter_by(swap_id=swap.id).all()
        notified_ids = {n.notified_doctor_id for n in notifs}
        assert doc2.id not in notified_ids


def test_accept_swap_reassigns_schedule(app):
    """Aceitar troca deve reatribuir o schedule para o médico aceitante."""
    doc1 = make_doctor(app, login='doc1', crm='C001')
    doc2 = make_doctor(app, login='doc2', crm='C002')
    loc = make_location(app)
    make_link(app, doc1.id, loc.id, 'DIARISTA')
    make_link(app, doc2.id, loc.id, 'DIARISTA')
    w = make_window(app, year=2025)
    sched_id = _make_schedule(app, doc1.id, loc.id, w.id)

    with app.app_context():
        swap = request_swap(sched_id, doc1.id)
        swap_id = swap.id
        accept_swap(swap_id, doc2.id)

        updated = db.session.get(Schedule, sched_id)
        assert updated.doctor_id == doc2.id

        updated_swap = db.session.get(ScheduleSwap, swap_id)
        assert updated_swap.status == 'accepted'
        assert updated_swap.target_doctor_id == doc2.id


def test_accept_swap_not_eligible_raises(app):
    """Médico sem vínculo elegível não pode aceitar a troca."""
    doc1 = make_doctor(app, login='doc1', crm='C001')
    doc2 = make_doctor(app, login='doc2', crm='C002')
    doc3 = make_doctor(app, login='doc3', crm='C003')
    loc = make_location(app)
    make_link(app, doc1.id, loc.id, 'DIARISTA')
    make_link(app, doc2.id, loc.id, 'DIARISTA')
    # doc3 sem vínculo com o local → não é elegível
    w = make_window(app, year=2025)
    sched_id = _make_schedule(app, doc1.id, loc.id, w.id)

    with app.app_context():
        swap = request_swap(sched_id, doc1.id)
        with pytest.raises(ValueError, match='habilitado'):
            accept_swap(swap.id, doc3.id)


def test_accept_swap_allows_newly_eligible_doctor_without_notification(app):
    """Médico que ganhou vínculo após a solicitação (sem SwapNotification)
    deve poder aceitar, pois a elegibilidade é verificada ao vivo."""
    doc1 = make_doctor(app, login='doc1', crm='C001')
    doc2 = make_doctor(app, login='doc2', crm='C002')
    doc3 = make_doctor(app, login='doc3', crm='C003')
    loc = make_location(app)
    make_link(app, doc1.id, loc.id, 'DIARISTA')
    make_link(app, doc2.id, loc.id, 'DIARISTA')
    w = make_window(app, year=2025)
    sched_id = _make_schedule(app, doc1.id, loc.id, w.id)

    with app.app_context():
        swap = request_swap(sched_id, doc1.id)

        notifs = SwapNotification.query.filter_by(swap_id=swap.id).all()
        notified_ids = {n.notified_doctor_id for n in notifs}
        assert doc3.id not in notified_ids

        # doc3 ganha vínculo após a solicitação
        make_link(app, doc3.id, loc.id, 'DIARISTA')

        accept_swap(swap.id, doc3.id)
        updated = db.session.get(Schedule, sched_id)
        assert updated.doctor_id == doc3.id


def test_build_swap_view_data_open_vs_resolved(app):
    """Para uma troca aberta, retorna médicos elegíveis e dias=0; após aceita,
    não exibe mais médicos disponíveis nem dias em aberto."""
    doc1 = make_doctor(app, login='doc1', crm='C001')
    doc2 = make_doctor(app, login='doc2', crm='C002')
    loc = make_location(app)
    make_link(app, doc1.id, loc.id, 'DIARISTA')
    make_link(app, doc2.id, loc.id, 'DIARISTA')
    w = make_window(app, year=2025)
    sched_id = _make_schedule(app, doc1.id, loc.id, w.id)

    with app.app_context():
        from app.models.user import User
        doctors = {u.id: u for u in User.query.all()}

        swap = request_swap(sched_id, doc1.id)

        eligible_by_swap, eligible_names_by_swap, days_open_by_swap = build_swap_view_data(
            [swap], doctors
        )
        assert doc2.id in eligible_by_swap[swap.id]
        assert doctors[doc2.id].name in eligible_names_by_swap[swap.id]
        assert days_open_by_swap[swap.id] == 0

        accept_swap(swap.id, doc2.id)
        swap = db.session.get(ScheduleSwap, swap.id)

        eligible_by_swap, eligible_names_by_swap, days_open_by_swap = build_swap_view_data(
            [swap], doctors
        )
        assert eligible_by_swap[swap.id] == []
        assert eligible_names_by_swap[swap.id] == '—'
        assert days_open_by_swap[swap.id] is None


def test_cancel_swap(app):
    """Médico cancela sua própria solicitação aberta."""
    doc1 = make_doctor(app, login='doc1', crm='C001')
    doc2 = make_doctor(app, login='doc2', crm='C002')
    loc = make_location(app)
    make_link(app, doc1.id, loc.id, 'DIARISTA')
    make_link(app, doc2.id, loc.id, 'DIARISTA')
    w = make_window(app, year=2025)
    sched_id = _make_schedule(app, doc1.id, loc.id, w.id)

    with app.app_context():
        swap = request_swap(sched_id, doc1.id)
        cancel_swap(swap.id, doc1.id)

        updated = db.session.get(ScheduleSwap, swap.id)
        assert updated.status == 'cancelled'


def test_admin_force_swap_ignores_restrictions(app):
    """ADMIN pode forçar troca mesmo com restrição do médico alvo."""
    doc1 = make_doctor(app, login='doc1', crm='C001')
    doc2 = make_doctor(app, login='doc2', crm='C002')
    loc = make_location(app)
    make_link(app, doc1.id, loc.id, 'DIARISTA')
    make_link(app, doc2.id, loc.id, 'DIARISTA')
    w = make_window(app, year=2025)
    target = date(2025, 6, 1)
    sched_id = _make_schedule(app, doc1.id, loc.id, w.id, day=target)

    with app.app_context():
        db.session.add(DoctorRestriction(
            doctor_id=doc2.id, window_id=w.id, restricted_date=target
        ))
        # Cria o swap manualmente (doc2 tem restrição, não seria notificado)
        swap = ScheduleSwap(requester_id=doc1.id, schedule_id=sched_id)
        db.session.add(swap)
        db.session.commit()

        admin_force_swap(swap.id, doc2.id)

        updated = db.session.get(Schedule, sched_id)
        assert updated.doctor_id == doc2.id

        updated_swap = db.session.get(ScheduleSwap, swap.id)
        assert updated_swap.status == 'accepted'


def test_duplicate_swap_request_raises(app):
    """Segunda solicitação de troca para o mesmo slot deve ser rejeitada."""
    doc1 = make_doctor(app, login='doc1', crm='C001')
    doc2 = make_doctor(app, login='doc2', crm='C002')
    loc = make_location(app)
    make_link(app, doc1.id, loc.id, 'DIARISTA')
    make_link(app, doc2.id, loc.id, 'DIARISTA')
    w = make_window(app, year=2025)
    sched_id = _make_schedule(app, doc1.id, loc.id, w.id)

    with app.app_context():
        request_swap(sched_id, doc1.id)
        with pytest.raises(ValueError, match='[Jj]á existe uma solicitação'):
            request_swap(sched_id, doc1.id)


def test_swap_wrong_doctor_raises(app):
    """Médico não pode solicitar troca de escala de outro médico."""
    doc1 = make_doctor(app, login='doc1', crm='C001')
    doc2 = make_doctor(app, login='doc2', crm='C002')
    loc = make_location(app)
    make_link(app, doc1.id, loc.id, 'DIARISTA')
    w = make_window(app, year=2025)
    sched_id = _make_schedule(app, doc1.id, loc.id, w.id)

    with app.app_context():
        with pytest.raises(ValueError, match='suas próprias escalas'):
            request_swap(sched_id, doc2.id)
