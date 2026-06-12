"""Testes unitários para helpers de calendário/navegação por mês."""
from app.utils.calendar_helpers import month_nav_disabled, default_schedule_month


class _Window:
    def __init__(self, year):
        self.year = year


def test_month_nav_disabled_only_for_2026_jan_to_may():
    w2026 = _Window(2026)
    assert month_nav_disabled(w2026, 1) is True
    assert month_nav_disabled(w2026, 5) is True
    assert month_nav_disabled(w2026, 6) is False
    assert month_nav_disabled(w2026, 12) is False

    w2025 = _Window(2025)
    assert month_nav_disabled(w2025, 1) is False


def test_default_schedule_month_skips_disabled_months_for_2026():
    window = _Window(2026)
    assert default_schedule_month(window, 1) == 6
    assert default_schedule_month(window, 5) == 6
    assert default_schedule_month(window, 6) == 6
    assert default_schedule_month(window, 7) == 7


def test_default_schedule_month_is_noop_for_other_years():
    window = _Window(2025)
    assert default_schedule_month(window, 1) == 1
    assert default_schedule_month(window, 12) == 12
