"""
Fixtures compartilhadas para todos os testes.
Cada helper usa with app.app_context() explicitamente, garantindo
que cada operação de DB use uma sessão limpa e independente.
"""
import os
import pytest
from sqlalchemy import text

os.environ.setdefault(
    'TEST_DATABASE_URL',
    'postgresql://postgres:postgres@localhost:5432/escala_medica_test',
)
os.environ.setdefault('FLASK_ENV', 'testing')

from app import create_app
from app.extensions import db as _db
from app.models.user import User
from app.models.location import Location, DoctorLocationLink
from app.models.schedule import (
    FillingWindow, DoctorRoutine, DoctorRestriction,
    Schedule, DoctorWindowConfirmation,
)
from app.models.swap import ScheduleSwap, SwapNotification
from app.models.audit import AuditLog

_TRUNCATE_SQL = text(
    "TRUNCATE TABLE swap_notifications, schedule_swaps, schedules, "
    "doctor_window_confirmations, doctor_restrictions, doctor_routines, "
    "filling_windows, doctor_location_links, locations, audit_log, users, "
    "med_news_items "
    "CASCADE"
)


@pytest.fixture(scope='session')
def app():
    return create_app('testing')


@pytest.fixture(autouse=True)
def clean_db(app):
    """Limpa todas as tabelas após cada teste."""
    yield
    with app.app_context():
        _db.session.execute(_TRUNCATE_SQL)
        _db.session.commit()


# ── Helpers de criação (cada um usa seu próprio app_context) ─────────────────

class _Ref:
    """Container para retornar IDs de objetos criados em contextos separados."""
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def make_admin(app, login='admin', name='Admin Test'):
    with app.app_context():
        u = User(name=name, login=login, email=f'{login}@test.com', role='admin')
        u.set_password('admin123')
        _db.session.add(u)
        _db.session.commit()
        return _Ref(id=u.id, login=login)


def make_doctor(app, login='doc1', name='Dr. Teste', crm='CRM001'):
    with app.app_context():
        u = User(name=name, crm=crm, login=login, email=f'{login}@test.com', role='medico')
        u.set_password('doc123')
        _db.session.add(u)
        _db.session.commit()
        return _Ref(id=u.id, login=login)


def make_location(app, name='UPA Norte', scale_type='DIARISTA'):
    with app.app_context():
        loc = Location(name=name, scale_type=scale_type)
        _db.session.add(loc)
        _db.session.commit()
        return _Ref(id=loc.id, name=name, scale_type=scale_type)


def make_link(app, doctor_id, location_id, scale_type='DIARISTA'):
    with app.app_context():
        lk = DoctorLocationLink(
            doctor_id=doctor_id, location_id=location_id, scale_type=scale_type
        )
        _db.session.add(lk)
        _db.session.commit()
        return _Ref(id=lk.id)


def make_window(app, year=2025, status='open', created_by=None):
    with app.app_context():
        if created_by is None:
            # Cria um usuário admin temporário se necessário
            creator = User(name='_sys', login='_sys', email='_sys@sys.com', role='admin')
            creator.set_password('x')
            _db.session.add(creator)
            _db.session.flush()
            created_by = creator.id
        w = FillingWindow(year=year, status=status, created_by=created_by)
        _db.session.add(w)
        _db.session.commit()
        return _Ref(id=w.id, year=year, status=status)


# ── Client helpers ────────────────────────────────────────────────────────────

@pytest.fixture
def client(app):
    app.config['WTF_CSRF_ENABLED'] = False
    with app.test_client() as c:
        yield c


def login_as(client, login, password):
    return client.post(
        '/login',
        data={'login': login, 'password': password},
        follow_redirects=True,
    )
