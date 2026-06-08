"""
Algoritmo de geração automática da escala.

Lógica:
1. Para cada (location, scale_type) com vínculos ativos → slot diário durante o ano
2. Expande rotinas declaradas → cobre os slots correspondentes (source='routine')
3. Slots restantes são lacunas → distribui pelo médico elegível com menor carga
4. Elegibilidade: vínculo ativo + sem restrição na data + sem conflito de data

Regras:
- Médico não pode ter dois atendimentos no mesmo dia
- Restrições são respeitadas obrigatoriamente
- Distribuição igualitária das lacunas (menor carga primeiro)
"""
from datetime import date, timedelta
from collections import defaultdict

from app.extensions import db
from app.models.location import DoctorLocationLink
from app.models.schedule import FillingWindow, DoctorRoutine, DoctorRestriction, Schedule


def _week_of_month(d: date) -> int:
    return (d.day - 1) // 7 + 1


def generate_schedule(window_id: int) -> dict:
    """
    Gera a escala para uma janela de preenchimento.

    Retorna dict:
      total_slots      - total de slots no ano
      routine_slots    - slots cobertos por rotinas
      generated_slots  - slots preenchidos pelo algoritmo
      uncovered_slots  - list[dict] slots não preenchidos (sem médico elegível)
    """
    window = db.session.get(FillingWindow, window_id)
    if not window:
        raise ValueError(f'FillingWindow {window_id} não encontrada.')

    # Datas do ano inteiro
    start = date(window.year, 1, 1)
    end = date(window.year, 12, 31)
    all_dates: list[date] = []
    d = start
    while d <= end:
        all_dates.append(d)
        d += timedelta(days=1)

    # (loc_id, scale_type) → set de doctor_ids elegíveis
    links = DoctorLocationLink.query.filter_by(active=True).all()
    location_doctors: dict[tuple, set] = defaultdict(set)
    for lk in links:
        location_doctors[(lk.location_id, lk.scale_type)].add(lk.doctor_id)

    if not location_doctors:
        return dict(total_slots=0, routine_slots=0, generated_slots=0, uncovered_slots=[])

    # Restrições: doctor_id → set[date]
    restrictions_raw = DoctorRestriction.query.filter_by(window_id=window_id).all()
    restricted: dict[int, set] = defaultdict(set)
    for r in restrictions_raw:
        restricted[r.doctor_id].add(r.restricted_date)

    # Expandir rotinas em slots concretos
    routines = DoctorRoutine.query.filter_by(window_id=window_id).all()
    routine_slots: dict[tuple, int] = {}  # (date, loc_id, scale_type) → doctor_id

    for routine in routines:
        for day in all_dates:
            if day.weekday() != routine.day_of_week:
                continue
            if routine.frequency == 'weekly':
                applies = True
            elif routine.frequency in ('biweekly', 'monthly'):
                applies = _week_of_month(day) == routine.week_of_month
            else:
                applies = False
            if applies:
                key = (day, routine.location_id, routine.scale_type)
                routine_slots[key] = routine.doctor_id

    # Limpar agenda anterior desta janela
    Schedule.query.filter_by(window_id=window_id).delete()
    db.session.flush()

    # Contadores de carga e datas por médico
    doctor_dates: dict[int, set] = defaultdict(set)
    doctor_load: dict[int, int] = defaultdict(int)

    # Criar entradas de rotina
    for (day, loc_id, scale_type), doctor_id in routine_slots.items():
        db.session.add(Schedule(
            window_id=window_id, date=day,
            location_id=loc_id, scale_type=scale_type,
            doctor_id=doctor_id, source='routine', status='draft',
        ))
        doctor_dates[doctor_id].add(day)
        doctor_load[doctor_id] += 1

    # Calcular todas as lacunas
    all_slots: set[tuple] = set()
    for (loc_id, scale_type) in location_doctors:
        for day in all_dates:
            all_slots.add((day, loc_id, scale_type))

    gaps = sorted(all_slots - set(routine_slots.keys()))

    generated_count = 0
    uncovered: list[dict] = []

    for (day, loc_id, scale_type) in gaps:
        eligible = [
            did for did in location_doctors[(loc_id, scale_type)]
            if day not in restricted[did]
            and day not in doctor_dates[did]
        ]

        if not eligible:
            uncovered.append({'date': day, 'location_id': loc_id, 'scale_type': scale_type})
            continue

        chosen = min(eligible, key=lambda did: doctor_load[did])
        db.session.add(Schedule(
            window_id=window_id, date=day,
            location_id=loc_id, scale_type=scale_type,
            doctor_id=chosen, source='generated', status='draft',
        ))
        doctor_dates[chosen].add(day)
        doctor_load[chosen] += 1
        generated_count += 1

    db.session.commit()

    return dict(
        total_slots=len(all_slots),
        routine_slots=len(routine_slots),
        generated_slots=generated_count,
        uncovered_slots=uncovered,
    )
