"""
Testes unitários do location_service.
Verifica: universo de posições, vínculo individual, propagação para todos
os médicos e backfill (premissa "todos vinculados a tudo por padrão").
"""
from datetime import date

from app.extensions import db
from app.models.location import DoctorLocationLink, LocationScaleRequirement
from app.models.schedule import CoverageAcceptance, DoctorRoutine
from app.services.location_service import (
    get_position_universe, set_doctor_link, link_doctor_to_all_positions,
    add_new_position, remove_position, sync_all_doctor_links,
)
from tests.conftest import make_doctor, make_location, make_link, make_window


def test_get_position_universe(app):
    """Retorna todas as combinações (location, scale_type) distintas conhecidas."""
    doc1 = make_doctor(app, login='doc1', crm='C001')
    doc2 = make_doctor(app, login='doc2', crm='C002')
    loc1 = make_location(app, name='UPA Norte')
    loc2 = make_location(app, name='UPA Sul')
    make_link(app, doc1.id, loc1.id, 'P1')
    make_link(app, doc2.id, loc1.id, 'P2')
    make_link(app, doc1.id, loc2.id, 'P1')

    with app.app_context():
        universe = get_position_universe()
        assert set(universe) == {(loc1.id, 'P1'), (loc1.id, 'P2'), (loc2.id, 'P1')}


def test_link_doctor_to_all_positions(app):
    """Médico ganha vínculo ativo para todos os combos do universo."""
    doc1 = make_doctor(app, login='doc1', crm='C001')
    doc2 = make_doctor(app, login='doc2', crm='C002')
    loc = make_location(app, name='UPA Norte')
    make_link(app, doc1.id, loc.id, 'P1')
    make_link(app, doc2.id, loc.id, 'P1')
    make_link(app, doc2.id, loc.id, 'P2')

    with app.app_context():
        link_doctor_to_all_positions(doc1.id)
        db.session.commit()

        links = {(lk.location_id, lk.scale_type): lk.active
                 for lk in DoctorLocationLink.query.filter_by(doctor_id=doc1.id).all()}
        assert links == {(loc.id, 'P1'): True, (loc.id, 'P2'): True}


def test_set_doctor_link_toggle(app):
    """Cria, desativa e reativa o mesmo vínculo sem violar a unique constraint."""
    doc = make_doctor(app, login='doc1', crm='C001')
    loc = make_location(app, name='UPA Norte')

    with app.app_context():
        set_doctor_link(doc.id, loc.id, 'P1', True)
        db.session.commit()
        lk = DoctorLocationLink.query.filter_by(doctor_id=doc.id, location_id=loc.id, scale_type='P1').first()
        assert lk.active is True

        set_doctor_link(doc.id, loc.id, 'P1', False)
        db.session.commit()
        lk = db.session.get(DoctorLocationLink, lk.id)
        assert lk.active is False

        set_doctor_link(doc.id, loc.id, 'P1', True)
        db.session.commit()
        lk = db.session.get(DoctorLocationLink, lk.id)
        assert lk.active is True


def test_add_new_position_links_all_doctors(app):
    """Nova posição é vinculada ativa para todos os médicos existentes."""
    doc1 = make_doctor(app, login='doc1', crm='C001')
    doc2 = make_doctor(app, login='doc2', crm='C002')
    loc = make_location(app, name='UPA Norte')
    make_link(app, doc1.id, loc.id, 'P1')

    with app.app_context():
        add_new_position(loc.id, 'P9')
        db.session.commit()

        for doc_id in (doc1.id, doc2.id):
            lk = DoctorLocationLink.query.filter_by(
                doctor_id=doc_id, location_id=loc.id, scale_type='P9').first()
            assert lk is not None
            assert lk.active is True


def test_remove_position_cleans_up_dependencies(app):
    """Remover uma posição desvincula todos os médicos e limpa requisito,
    aceite de lacuna e rotina desse (local, tipo de escala)."""
    doc = make_doctor(app, login='doc1', crm='C001')
    loc = make_location(app, name='UPA Norte')
    make_link(app, doc.id, loc.id, 'P1')
    make_link(app, doc.id, loc.id, 'P2')
    win = make_window(app, year=2030)

    with app.app_context():
        db.session.add(LocationScaleRequirement(location_id=loc.id, scale_type='P2', required=False))
        db.session.add(CoverageAcceptance(window_id=win.id, location_id=loc.id, date=date(2030, 1, 1),
                                           scale_type='P2', justification='teste', created_by=doc.id))
        db.session.add(DoctorRoutine(doctor_id=doc.id, location_id=loc.id, window_id=win.id,
                                      frequency='weekly', day_of_week=0, scale_type='P2'))
        db.session.commit()

        remove_position(loc.id, 'P2')
        db.session.commit()

        assert DoctorLocationLink.query.filter_by(location_id=loc.id, scale_type='P2').count() == 0
        assert LocationScaleRequirement.query.filter_by(location_id=loc.id, scale_type='P2').count() == 0
        assert CoverageAcceptance.query.filter_by(location_id=loc.id, scale_type='P2').count() == 0
        assert DoctorRoutine.query.filter_by(location_id=loc.id, scale_type='P2').count() == 0

        universe = get_position_universe()
        assert (loc.id, 'P2') not in universe
        assert (loc.id, 'P1') in universe


def test_sync_all_doctor_links_backfills_missing(app):
    """Médico sem vínculo recebe todos os combos do universo após o sync."""
    doc1 = make_doctor(app, login='doc1', crm='C001')
    doc2 = make_doctor(app, login='doc2', crm='C002')
    loc1 = make_location(app, name='UPA Norte')
    loc2 = make_location(app, name='UPA Sul')
    make_link(app, doc1.id, loc1.id, 'P1')
    make_link(app, doc1.id, loc2.id, 'P2')
    # doc2 não tem nenhum vínculo

    with app.app_context():
        sync_all_doctor_links()

        links = {(lk.location_id, lk.scale_type): lk.active
                 for lk in DoctorLocationLink.query.filter_by(doctor_id=doc2.id).all()}
        assert links == {(loc1.id, 'P1'): True, (loc2.id, 'P2'): True}
