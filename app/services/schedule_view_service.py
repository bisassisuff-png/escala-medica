"""
Dados de exibição da grade de escala (calendário, KPIs, lacunas, exceções),
compartilhados entre a visão de revisão do admin (`admin.schedule_review`) e
a visão somente-leitura do médico (`doctor.group_schedule`).
"""
from collections import defaultdict
from datetime import date as date_type, timedelta

from app.models.location import Location, DoctorLocationLink, get_required_loc_keys
from app.models.schedule import Schedule, Holiday, CoverageException, CoverageAcceptance
from app.models.user import User
from app.utils.calendar_helpers import (
    build_calendar_weeks, group_entries_by_date, location_palette,
    location_abbr, last_day_of_month, WEEKDAY_NAMES,
)


def get_schedule_review_context(window, month):
    """Retorna os dados de exibição (calendário, KPIs, lacunas, exceções)
    para a janela e mês informados."""
    start_m = date_type(window.year, month, 1)
    end_m = last_day_of_month(window.year, month)

    entries = (Schedule.query
               .filter_by(window_id=window.id)
               .filter(Schedule.date >= start_m, Schedule.date <= end_m)
               .order_by(Schedule.date, Schedule.location_id)
               .all())

    stats = {
        'total':     Schedule.query.filter_by(window_id=window.id).count(),
        'routine':   Schedule.query.filter_by(window_id=window.id, source='routine').count(),
        'generated': Schedule.query.filter_by(window_id=window.id, source='generated').count(),
    }

    # Lacunas: (location, scale_type) × (data) sem cobertura
    all_links = DoctorLocationLink.query.filter_by(active=True).all()
    loc_keys = get_required_loc_keys(all_links)
    covered = {(e.date, e.location_id, e.scale_type) for e in entries}

    exceptions = (CoverageException.query
                  .filter(CoverageException.window_id == window.id,
                          CoverageException.date >= start_m,
                          CoverageException.date <= end_m)
                  .all())
    exceptions_by_loc_date = {(e.date, e.location_id): e for e in exceptions}
    excepted_locations_by_date = defaultdict(set)
    for e in exceptions:
        excepted_locations_by_date[e.date].add(e.location_id)

    acceptances = (CoverageAcceptance.query
                   .filter(CoverageAcceptance.window_id == window.id,
                           CoverageAcceptance.date >= start_m,
                           CoverageAcceptance.date <= end_m)
                   .all())
    acceptances_by_key = {(a.date, a.location_id, a.scale_type): a for a in acceptances}

    uncovered = []
    gaps_by_loc_date = defaultdict(list)
    d = start_m
    while d <= end_m:
        excepted = excepted_locations_by_date.get(d, set())
        for (loc_id, sc) in loc_keys:
            if loc_id in excepted:
                continue
            if (d, loc_id, sc) not in covered:
                acc = acceptances_by_key.get((d, loc_id, sc))
                gaps_by_loc_date[(d, loc_id)].append({'scale_type': sc, 'acceptance': acc})
                if acc is None:
                    uncovered.append({'date': d, 'location_id': loc_id, 'scale_type': sc})
        d += timedelta(days=1)

    locations = {l.id: l for l in Location.query.all()}
    doctors = {u.id: u for u in User.query.filter_by(role='medico').all()}
    month_names = ['','Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez']

    calendar_weeks = build_calendar_weeks(window.year, month)
    entries_by_date = group_entries_by_date(entries)
    holidays_by_date = {h.date: h for h in Holiday.query.filter_by(window_id=window.id).all()}
    location_list = sorted(locations.values(), key=lambda l: l.id)
    loc_color = location_palette(location_list)
    loc_abbr = {l.id: location_abbr(l.name) for l in location_list}
    uncovered_by_date = defaultdict(list)
    for u in uncovered:
        uncovered_by_date[u['date']].append(u)

    return dict(
        entries=entries, stats=stats, uncovered=uncovered,
        locations=locations, doctors=doctors,
        month=month, month_names=month_names,
        calendar_weeks=calendar_weeks, entries_by_date=entries_by_date,
        holidays_by_date=holidays_by_date, location_list=location_list,
        loc_color=loc_color, loc_abbr=loc_abbr,
        uncovered_by_date=uncovered_by_date, today=date_type.today(),
        weekday_names=WEEKDAY_NAMES,
        exceptions_by_loc_date=exceptions_by_loc_date,
        gaps_by_loc_date=gaps_by_loc_date,
    )
