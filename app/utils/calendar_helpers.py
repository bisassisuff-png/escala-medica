import calendar as _calendar
from collections import defaultdict

WEEKDAY_NAMES = ['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb']
_PALETTE_SIZE = 5


def build_calendar_weeks(year, month):
    """Semanas (domingo a sábado) do mês, incluindo dias de preenchimento
    do mês anterior/seguinte."""
    return _calendar.Calendar(firstweekday=6).monthdatescalendar(year, month)


def last_day_of_month(year, month):
    from datetime import date as _date
    return _date(year, month, _calendar.monthrange(year, month)[1])


def group_entries_by_date(entries):
    grouped = defaultdict(list)
    for entry in entries:
        grouped[entry.date].append(entry)
    return grouped


def location_palette(locations):
    """Mapeia location.id -> índice de cor (0..4), cíclico."""
    return {loc.id: i % _PALETTE_SIZE for i, loc in enumerate(sorted(locations, key=lambda l: l.id))}


def location_abbr(name):
    """'Hospital Santa Rita' -> 'SR', 'CIAS' -> 'CIAS'."""
    words = [w for w in name.split() if w.lower() != 'hospital']
    if len(words) == 1:
        return words[0][:4].upper()
    return ''.join(w[0] for w in words).upper()


def month_nav_disabled(window, month):
    """Mês sem dados importados para esta janela (regra 2026: jan-mai)."""
    return window.year == 2026 and month < 6


def default_schedule_month(window, month):
    """Se `month` estiver desabilitado para esta janela, retorna o primeiro
    mês com navegação ativa (ex.: 2026 -> junho); senão retorna `month`."""
    if not month_nav_disabled(window, month):
        return month
    for m in range(1, 13):
        if not month_nav_disabled(window, m):
            return m
    return month
