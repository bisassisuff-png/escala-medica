"""
Algoritmo de geração automática da escala.

Regras:
1. SR P1 cobre também SR Doppler e Apart P2 no mesmo dia
2. Apart P1 cobre também SR P2 no mesmo dia
3. Preferência por médicos do sobreaviso do CIAS em SR e Apart
4. Feriados prolongados (2ª/3ª → Sáb/Dom anterior; 5ª/6ª → Sáb/Dom seguinte)
   herdados do médico que cobriu o fim de semana adjacente
5. Distribuição justa dos feriados prolongados entre os profissionais de fim de semana
- Restrições cadastradas são sempre respeitadas
- Médico pode acumular slots em locais diferentes no mesmo dia
"""
from datetime import date, timedelta
from collections import defaultdict

from app.extensions import db
from app.models.location import DoctorLocationLink
from app.models.schedule import FillingWindow, DoctorRoutine, DoctorRestriction, Schedule, Holiday


def _week_of_month(d: date) -> int:
    return (d.day - 1) // 7 + 1


def _resolve_location_ids():
    """Retorna (sr_id, apart_id, cias_id) resolvidos por nome. None se ausente."""
    from app.models.location import Location
    sr = Location.query.filter(Location.name.ilike('%santa rita%')).first()
    apart = Location.query.filter(Location.name.ilike('%apart%')).first()
    cias = Location.query.filter(Location.name.ilike('%cias%')).first()
    return (
        sr.id if sr else None,
        apart.id if apart else None,
        cias.id if cias else None,
    )


def _implied_slots(loc_id, scale_type, sr_id, apart_id):
    """
    Regra 1: SR P1 → [(SR, Doppler), (Apart, P2)]
    Regra 2: Apart P1 → [(SR, P2)]
    """
    if sr_id and apart_id:
        if loc_id == sr_id and scale_type == 'P1':
            return [(sr_id, 'Doppler'), (apart_id, 'P2')]
        if loc_id == apart_id and scale_type == 'P1':
            return [(sr_id, 'P2')]
    return []


def _extended_holiday_refs(d: date, holiday_set: set):
    """
    Regra 4: se d é feriado prolongado, retorna [Sáb, Dom] de referência.
    2ª/3ª → fim de semana anterior; 5ª/6ª → fim de semana seguinte.
    Retorna None se não se aplica.
    """
    if d not in holiday_set:
        return None
    dow = d.weekday()  # 0=Seg, 1=Ter, 3=Qui, 4=Sex
    if dow == 0:    # Segunda → Sáb/Dom anterior
        return [d - timedelta(2), d - timedelta(1)]
    if dow == 1:    # Terça → Sáb/Dom anterior
        return [d - timedelta(3), d - timedelta(2)]
    if dow == 3:    # Quinta → Sáb/Dom seguinte
        return [d + timedelta(2), d + timedelta(3)]
    if dow == 4:    # Sexta → Sáb/Dom seguinte
        return [d + timedelta(1), d + timedelta(2)]
    return None


def generate_schedule(window_id: int) -> dict:
    """
    Gera a escala para uma janela de preenchimento.

    Retorna dict:
      total_slots      - total de slots no ano
      routine_slots    - slots cobertos por rotinas
      generated_slots  - slots preenchidos pelo algoritmo
      uncovered_slots  - list[dict] slots não preenchidos
    """
    window = db.session.get(FillingWindow, window_id)
    if not window:
        raise ValueError(f'FillingWindow {window_id} não encontrada.')

    sr_id, apart_id, cias_id = _resolve_location_ids()

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
    restricted: dict[int, set] = defaultdict(set)
    for r in DoctorRestriction.query.filter_by(window_id=window_id).all():
        restricted[r.doctor_id].add(r.restricted_date)

    # ── Expansão de rotinas ───────────────────────────────────────────────────
    routine_slots: dict[tuple, int] = {}  # (date, loc, scale) → doctor_id
    for routine in DoctorRoutine.query.filter_by(window_id=window_id).all():
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
                routine_slots[(day, routine.location_id, routine.scale_type)] = routine.doctor_id

    # ── Cobertura implícita das rotinas (Regras 1 & 2) ───────────────────────
    implied_from_routines: dict[tuple, int] = {}
    for (day, loc, scale), doc in routine_slots.items():
        for (iloc, iscale) in _implied_slots(loc, scale, sr_id, apart_id):
            key = (day, iloc, iscale)
            if key not in routine_slots and key not in implied_from_routines:
                implied_from_routines[key] = doc

    all_covered: dict[tuple, int] = {**routine_slots, **implied_from_routines}

    # ── Limpar escala anterior e gravar rotinas + implied ────────────────────
    Schedule.query.filter_by(window_id=window_id).delete()
    db.session.flush()

    for (day, loc, scale), doc in all_covered.items():
        source = 'routine' if (day, loc, scale) in routine_slots else 'generated'
        db.session.add(Schedule(
            window_id=window_id, date=day,
            location_id=loc, scale_type=scale,
            doctor_id=doc, source=source, status='draft',
        ))

    # ── Estado de rastreamento ────────────────────────────────────────────────
    doctor_load: dict[int, int] = defaultdict(int)
    day_assignments: dict[date, dict[tuple, int]] = defaultdict(dict)
    for (day, loc, scale), doc in all_covered.items():
        doctor_load[doc] += 1
        day_assignments[day][(loc, scale)] = doc

    # ── Feriados ──────────────────────────────────────────────────────────────
    holiday_set = {h.date for h in Holiday.query.filter_by(window_id=window_id).all()}

    # ── Calcular gaps e separar feriados prolongados ──────────────────────────
    all_slots: set[tuple] = set()
    for (loc, scale) in location_doctors:
        for day in all_dates:
            all_slots.add((day, loc, scale))

    gaps = sorted(all_slots - set(all_covered.keys()))

    regular_gaps: list[tuple] = []
    ext_holiday_gaps: list[tuple] = []
    for gap in gaps:
        day, loc, scale = gap
        refs = _extended_holiday_refs(day, holiday_set)
        # Apenas SR e Apart entram na lógica de feriado prolongado
        if refs and loc in (sr_id, apart_id) and sr_id and apart_id:
            ext_holiday_gaps.append(gap)
        else:
            regular_gaps.append(gap)

    generated_count = 0
    uncovered: list[dict] = []

    # ── Helper: criar slot + aplicar cobertura implícita ─────────────────────
    def _assign(doc_id, day, loc, scale, source='generated'):
        nonlocal generated_count
        if (day, loc, scale) in day_assignments[day]:
            return  # já coberto
        db.session.add(Schedule(
            window_id=window_id, date=day,
            location_id=loc, scale_type=scale,
            doctor_id=doc_id, source=source, status='draft',
        ))
        day_assignments[day][(loc, scale)] = doc_id
        doctor_load[doc_id] += 1
        generated_count += 1
        # Cobertura implícita (Regras 1 & 2)
        for (iloc, iscale) in _implied_slots(loc, scale, sr_id, apart_id):
            if (iloc, iscale) not in day_assignments[day]:
                db.session.add(Schedule(
                    window_id=window_id, date=day,
                    location_id=iloc, scale_type=iscale,
                    doctor_id=doc_id, source='generated', status='draft',
                ))
                day_assignments[day][(iloc, iscale)] = doc_id
                doctor_load[doc_id] += 1
                generated_count += 1

    # ── Preencher gaps regulares (Regra 3) ────────────────────────────────────
    for (day, loc, scale) in regular_gaps:
        if (loc, scale) in day_assignments[day]:
            continue  # coberto via implied de slot anterior

        eligible = [
            did for did in location_doctors[(loc, scale)]
            if day not in restricted[did]
        ]
        if not eligible:
            uncovered.append({'date': day, 'location_id': loc, 'scale_type': scale})
            continue

        # Regra 3: preferir médicos já alocados no CIAS neste dia
        if cias_id and loc in (sr_id, apart_id):
            cias_today = {
                doc for (l, _s), doc in day_assignments[day].items()
                if l == cias_id
            }
            preferred = [d for d in eligible if d in cias_today]
            rest = [d for d in eligible if d not in cias_today]
            ordered = preferred + rest
        else:
            ordered = eligible

        # Escolhe com menor carga dentro do grupo preferido; fallback no resto
        preferred_group = [d for d in ordered if d in (
            {d for d in ordered[:len(ordered) // 2 + 1]}  # todos preferred primeiro
        )]
        # Simplificado: pega o min da lista ordered já ordenada por preferência
        chosen = min(ordered, key=lambda did: (
            0 if cias_id and loc in (sr_id, apart_id) and did in {
                doc for (l, _s), doc in day_assignments[day].items() if l == cias_id
            } else 1,
            doctor_load[did]
        ))
        _assign(chosen, day, loc, scale)

    # ── Preencher feriados prolongados (Regras 4 & 5) ────────────────────────
    extended_holiday_load: dict[int, int] = defaultdict(int)

    for (day, loc, scale) in ext_holiday_gaps:
        if (loc, scale) in day_assignments[day]:
            continue  # já coberto via implied ou rotina

        refs = _extended_holiday_refs(day, holiday_set)
        # Médicos que cobriram o fim de semana de referência nesta mesma posição
        weekend_docs: list[int] = []
        for ref_date in refs:
            doc = day_assignments[ref_date].get((loc, scale))
            if doc is not None:
                weekend_docs.append(doc)

        # Remove duplicatas mantendo ordem
        seen: set[int] = set()
        weekend_docs_unique = [d for d in weekend_docs if not (d in seen or seen.add(d))]

        eligible_weekend = [
            d for d in weekend_docs_unique
            if day not in restricted[d]
        ]

        if eligible_weekend:
            # Regra 5: prefere quem tem menos feriados prolongados acumulados
            chosen = min(eligible_weekend, key=lambda d: (extended_holiday_load[d], doctor_load[d]))
            _assign(chosen, day, loc, scale)
            extended_holiday_load[chosen] += 1
        else:
            # Fallback: trata como gap regular com preferência CIAS
            eligible = [
                did for did in location_doctors[(loc, scale)]
                if day not in restricted[did]
            ]
            if not eligible:
                uncovered.append({'date': day, 'location_id': loc, 'scale_type': scale})
                continue
            if cias_id:
                cias_today = {
                    doc for (l, _s), doc in day_assignments[day].items()
                    if l == cias_id
                }
                chosen = min(eligible, key=lambda did: (
                    0 if did in cias_today else 1,
                    doctor_load[did],
                ))
            else:
                chosen = min(eligible, key=lambda did: doctor_load[did])
            _assign(chosen, day, loc, scale)

    db.session.commit()

    return dict(
        total_slots=len(all_slots),
        routine_slots=len(routine_slots),
        generated_slots=generated_count,
        uncovered_slots=uncovered,
    )
