"""
Serviço de KPIs para o dashboard administrativo.
Todas as consultas são feitas sob demanda (sem cache).
"""
import calendar
from datetime import date, timedelta
from collections import defaultdict
from sqlalchemy import func

from app.extensions import db
from app.models.schedule import Schedule, FillingWindow, DoctorRestriction, CoverageException, CoverageAcceptance
from app.models.swap import ScheduleSwap
from app.models.user import User
from app.models.location import Location, get_required_loc_keys


def _month_range(year: int, month: int):
    last = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last)


def get_coverage_summary(window_id: int, month: int) -> dict:
    """Resumo de cobertura (slots esperados x cobertos) para window+mês,
    descontando exceções (CoverageException) e aceites (CoverageAcceptance)."""
    window = db.session.get(FillingWindow, window_id)
    start, end = _month_range(window.year, month)

    loc_keys = get_required_loc_keys()

    covered = {(e.date, e.location_id, e.scale_type)
               for e in Schedule.query.filter(
                   Schedule.window_id == window_id,
                   Schedule.date >= start, Schedule.date <= end).all()}

    excepted_by_date = defaultdict(set)
    for e in CoverageException.query.filter(
            CoverageException.window_id == window_id,
            CoverageException.date >= start, CoverageException.date <= end).all():
        excepted_by_date[e.date].add(e.location_id)

    accepted = {(a.date, a.location_id, a.scale_type)
                for a in CoverageAcceptance.query.filter(
                    CoverageAcceptance.window_id == window_id,
                    CoverageAcceptance.date >= start, CoverageAcceptance.date <= end).all()}

    total = uncovered = 0
    d = start
    while d <= end:
        excepted = excepted_by_date.get(d, set())
        for (loc_id, sc) in loc_keys:
            if loc_id in excepted:
                continue
            total += 1
            if (d, loc_id, sc) not in covered and (d, loc_id, sc) not in accepted:
                uncovered += 1
        d += timedelta(days=1)

    covered_n = total - uncovered
    pct = round(covered_n / total * 100, 1) if total else 100.0
    return {'total': total, 'covered': covered_n, 'uncovered': uncovered, 'pct': pct}


def get_dashboard_data(window_id: int, month: int) -> dict:
    """
    Retorna todos os KPIs do mês selecionado para o dashboard.
    Inclui dados do mês anterior para comparativo.
    """
    window = db.session.get(FillingWindow, window_id)
    if not window:
        return {}

    year = window.year
    start, end = _month_range(year, month)

    doctors = {u.id: u for u in User.query.filter_by(role='medico').all()}
    locations = {l.id: l for l in Location.query.all()}

    # ── Plantões por médico no mês ────────────────────────────────────────────
    doc_total_rows = (db.session.query(Schedule.doctor_id, func.count().label('c'))
                      .filter(Schedule.window_id == window_id,
                              Schedule.date.between(start, end))
                      .group_by(Schedule.doctor_id)
                      .all())
    doctor_totals = {r.doctor_id: r.c for r in doc_total_rows}

    # ── Plantões por médico × local no mês ────────────────────────────────────
    doc_loc_rows = (db.session.query(
        Schedule.doctor_id, Schedule.location_id, func.count().label('c'))
        .filter(Schedule.window_id == window_id,
                Schedule.date.between(start, end))
        .group_by(Schedule.doctor_id, Schedule.location_id)
        .all())
    doctor_loc: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for r in doc_loc_rows:
        doctor_loc[r.doctor_id][r.location_id] = r.c

    # ── Distribuição por dia da semana no mês ─────────────────────────────────
    weekday_counts: dict[int, int] = defaultdict(int)
    date_rows = (db.session.query(Schedule.date, func.count().label('c'))
                 .filter(Schedule.window_id == window_id,
                         Schedule.date.between(start, end))
                 .group_by(Schedule.date)
                 .all())
    for r in date_rows:
        weekday_counts[r.date.weekday()] += r.c

    # ── Mês anterior (para comparativo) ──────────────────────────────────────
    prev_m = month - 1 if month > 1 else 12
    prev_y = year if month > 1 else year - 1
    prev_start, prev_end = _month_range(prev_y, prev_m)
    prev_rows = (db.session.query(Schedule.doctor_id, func.count().label('c'))
                 .filter(Schedule.window_id == window_id,
                         Schedule.date.between(prev_start, prev_end))
                 .group_by(Schedule.doctor_id)
                 .all())
    prev_totals = {r.doctor_id: r.c for r in prev_rows}

    # ── Trocas (ano todo da janela) ───────────────────────────────────────────
    def _swap_count(status):
        return (ScheduleSwap.query
                .join(Schedule, ScheduleSwap.schedule_id == Schedule.id)
                .filter(Schedule.window_id == window_id,
                        ScheduleSwap.status == status)
                .count())

    swap_open = _swap_count('open')
    swap_accepted = _swap_count('accepted')
    swap_cancelled = _swap_count('cancelled')

    # ── Restrições por médico (top 10) ────────────────────────────────────────
    restr_rows = (db.session.query(DoctorRestriction.doctor_id, func.count().label('c'))
                  .filter(DoctorRestriction.window_id == window_id)
                  .group_by(DoctorRestriction.doctor_id)
                  .order_by(func.count().desc())
                  .limit(10)
                  .all())

    # ── Cobertura global da escala (ano) ──────────────────────────────────────
    total_schedule = Schedule.query.filter_by(window_id=window_id).count()

    # ── Alertas de sobrecarga / subutilização (no mês) ────────────────────────
    avg = sum(doctor_totals.values()) / len(doctor_totals) if doctor_totals else 0
    overloaded = [did for did, c in doctor_totals.items() if c > avg * 1.3 and avg > 0]
    underloaded = [did for did, c in doctor_totals.items() if 0 < c < avg * 0.7]

    # ── Ranking (mês, decrescente) ────────────────────────────────────────────
    ranking = sorted(doctor_totals.items(), key=lambda x: x[1], reverse=True)

    # Versões serializáveis para JSON no template
    doc_ids = list(doctors.keys())
    doc_names = [doctors[did].name for did in doc_ids]
    loc_ids = list(locations.keys())
    loc_name_map = {lid: loc.name for lid, loc in locations.items()}

    return dict(
        doctors=doctors,
        locations=locations,
        doctor_totals=doctor_totals,
        doctor_loc={k: dict(v) for k, v in doctor_loc.items()},
        weekday_counts=dict(weekday_counts),
        prev_totals=prev_totals,
        swap_open=swap_open,
        swap_accepted=swap_accepted,
        swap_cancelled=swap_cancelled,
        restr_rows=restr_rows,
        total_schedule=total_schedule,
        overloaded=overloaded,
        underloaded=underloaded,
        ranking=ranking,
        avg_load=round(avg, 1),
        # JSON-safe
        doc_ids=doc_ids,
        doc_names=doc_names,
        loc_ids=loc_ids,
        loc_name_map=loc_name_map,
    )


def get_doctor_month_stats(doctor_id: int, window_id: int, month: int) -> dict:
    """KPIs individuais para o dashboard do médico."""
    window = db.session.get(FillingWindow, window_id)
    if not window:
        return {}

    year = window.year
    start, end = _month_range(year, month)

    total = (Schedule.query
             .filter_by(window_id=window_id, doctor_id=doctor_id)
             .filter(Schedule.date.between(start, end))
             .count())

    loc_rows = (db.session.query(Schedule.location_id, func.count().label('c'))
                .filter_by(window_id=window_id, doctor_id=doctor_id)
                .filter(Schedule.date.between(start, end))
                .group_by(Schedule.location_id)
                .all())
    locations = {l.id: l for l in Location.query.all()}
    by_location = [(locations.get(r.location_id), r.c) for r in loc_rows]

    upcoming = (Schedule.query
                .filter_by(window_id=window_id, doctor_id=doctor_id)
                .filter(Schedule.date >= date.today())
                .order_by(Schedule.date)
                .limit(5)
                .all())

    return dict(total=total, by_location=by_location, upcoming=upcoming,
                locations=locations)
