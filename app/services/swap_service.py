"""
Serviço de trocas de escala.

Fluxo:
1. Médico solicita troca de um slot seu (published)
2. Sistema identifica médicos elegíveis: vínculo ativo + livre no dia + sem restrição
3. Cria SwapNotification para cada elegível
4. Médico notificado aceita → schedule.doctor_id é reatribuído, swap fechado
5. ADMIN pode forçar qualquer troca sem restrições
"""
from datetime import date, datetime

from app.extensions import db
from app.models.schedule import Schedule, DoctorRestriction
from app.models.swap import ScheduleSwap, SwapNotification
from app.models.location import DoctorLocationLink


def find_eligible_doctors(schedule: Schedule) -> list[int]:
    """Médicos que podem cobrir o slot: vínculo ativo + livres no dia + sem restrição."""
    linked_ids = {
        lk.doctor_id
        for lk in DoctorLocationLink.query.filter_by(
            location_id=schedule.location_id,
            scale_type=schedule.scale_type,
            active=True,
        ).all()
    }
    linked_ids.discard(schedule.doctor_id)  # exclui o próprio solicitante

    restricted_ids = {
        r.doctor_id
        for r in DoctorRestriction.query.filter_by(
            restricted_date=schedule.date
        ).all()
    }

    busy_ids = {
        s.doctor_id
        for s in Schedule.query.filter_by(
            window_id=schedule.window_id,
            date=schedule.date,
        ).all()
    }
    busy_ids.discard(schedule.doctor_id)

    return list(linked_ids - restricted_ids - busy_ids)


def request_swap(schedule_id: int, requester_id: int) -> ScheduleSwap:
    """Cria uma solicitação de troca e notifica médicos elegíveis."""
    schedule = db.session.get(Schedule, schedule_id)
    if not schedule:
        raise ValueError('Escala não encontrada.')
    if schedule.doctor_id != requester_id:
        raise ValueError('Você só pode solicitar troca de suas próprias escalas.')
    if schedule.status != 'published':
        raise ValueError('Só é possível solicitar troca de escalas publicadas.')

    existing = ScheduleSwap.query.filter_by(
        schedule_id=schedule_id, status='open'
    ).first()
    if existing:
        raise ValueError('Já existe uma solicitação aberta para esta data.')

    swap = ScheduleSwap(requester_id=requester_id, schedule_id=schedule_id)
    db.session.add(swap)
    db.session.flush()

    eligible = find_eligible_doctors(schedule)
    for doctor_id in eligible:
        db.session.add(SwapNotification(swap_id=swap.id, notified_doctor_id=doctor_id))

    db.session.commit()
    return swap


def accept_swap(swap_id: int, accepting_doctor_id: int) -> None:
    """Médico aceita uma troca: reatribui o slot e fecha a solicitação."""
    swap = db.session.get(ScheduleSwap, swap_id)
    if not swap or swap.status != 'open':
        raise ValueError('Esta troca não está mais disponível.')

    schedule = db.session.get(Schedule, swap.schedule_id)
    if accepting_doctor_id not in find_eligible_doctors(schedule):
        raise ValueError('Você não está habilitado a cobrir este plantão.')

    schedule.doctor_id = accepting_doctor_id

    swap.target_doctor_id = accepting_doctor_id
    swap.status = 'accepted'
    swap.resolved_at = datetime.utcnow()

    SwapNotification.query.filter_by(swap_id=swap_id).update({'seen': True})
    db.session.commit()


def cancel_swap(swap_id: int, requester_id: int) -> None:
    """Médico cancela sua própria solicitação aberta."""
    swap = db.session.get(ScheduleSwap, swap_id)
    if not swap or swap.requester_id != requester_id:
        raise ValueError('Troca não encontrada.')
    if swap.status != 'open':
        raise ValueError('Só é possível cancelar trocas abertas.')

    swap.status = 'cancelled'
    swap.resolved_at = datetime.utcnow()
    SwapNotification.query.filter_by(swap_id=swap_id).update({'seen': True})
    db.session.commit()


def admin_force_swap(swap_id: int, target_doctor_id: int) -> None:
    """ADMIN atribui diretamente um médico à troca, sem restrições."""
    swap = db.session.get(ScheduleSwap, swap_id)
    if not swap or swap.status != 'open':
        raise ValueError('Esta troca já foi resolvida ou não existe.')

    schedule = db.session.get(Schedule, swap.schedule_id)
    schedule.doctor_id = target_doctor_id

    swap.target_doctor_id = target_doctor_id
    swap.status = 'accepted'
    swap.resolved_at = datetime.utcnow()
    SwapNotification.query.filter_by(swap_id=swap_id).update({'seen': True})
    db.session.commit()


def build_swap_view_data(swaps: list[ScheduleSwap], doctors: dict) -> tuple[dict, dict, dict]:
    """Dados auxiliares de exibição para uma lista de trocas, indexados por swap.id:
    médicos disponíveis para cobrir o plantão (elegibilidade ao vivo, só para trocas
    'open') e há quantos dias a troca está em aberto."""
    eligible_by_swap = {}
    eligible_names_by_swap = {}
    days_open_by_swap = {}
    today = date.today()
    for sw in swaps:
        if sw.status == 'open':
            eligible_ids = find_eligible_doctors(sw.schedule)
            days_open_by_swap[sw.id] = (today - sw.requested_at.date()).days
        else:
            eligible_ids = []
            days_open_by_swap[sw.id] = None
        eligible_by_swap[sw.id] = eligible_ids
        names = [doctors[d].name for d in eligible_ids if d in doctors]
        eligible_names_by_swap[sw.id] = ', '.join(names) if names else '—'
    return eligible_by_swap, eligible_names_by_swap, days_open_by_swap
