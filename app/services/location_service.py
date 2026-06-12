"""
Serviço de vínculos médico × local/posição.

Premissa: todo médico pode ser vinculado a qualquer local/posição (tipo de escala).
Por padrão, todo médico já está vinculado (ativo) a todo o "universo" de posições
conhecidas no sistema — o admin pode desvincular pontualmente em
"Cadastro > Médicos > Vínculos".
"""
from app.extensions import db
from app.models.location import DoctorLocationLink
from app.models.user import User


def get_position_universe():
    """(location_id, scale_type) já conhecidos no sistema (vínculo de algum médico)."""
    pairs = (db.session.query(DoctorLocationLink.location_id, DoctorLocationLink.scale_type)
             .filter(DoctorLocationLink.scale_type.isnot(None))
             .distinct().all())
    return sorted(set(pairs))


def set_doctor_link(doctor_id, location_id, scale_type, active):
    """Cria ou atualiza o vínculo (doctor_id, location_id, scale_type) -> active."""
    lk = DoctorLocationLink.query.filter_by(
        doctor_id=doctor_id, location_id=location_id, scale_type=scale_type).first()
    if lk is None:
        lk = DoctorLocationLink(doctor_id=doctor_id, location_id=location_id, scale_type=scale_type)
        db.session.add(lk)
    lk.active = active


def link_doctor_to_all_positions(doctor_id):
    """Vincula um médico a todas as posições já conhecidas (premissa "tudo por padrão")."""
    for location_id, scale_type in get_position_universe():
        set_doctor_link(doctor_id, location_id, scale_type, True)


def add_new_position(location_id, scale_type):
    """Registra uma posição nova (local + tipo de escala) e vincula TODOS os médicos a ela."""
    for doc in User.query.filter_by(role='medico').all():
        set_doctor_link(doc.id, location_id, scale_type, True)


def remove_position(location_id, scale_type):
    """Remove uma posição (local + tipo de escala) do sistema: desvincula
    todos os médicos e limpa registros dependentes (requisito de cobertura,
    aceites de lacuna e rotinas). Plantões já lançados em Schedule não são
    apagados."""
    from app.models.location import LocationScaleRequirement
    from app.models.schedule import CoverageAcceptance, DoctorRoutine

    DoctorLocationLink.query.filter_by(location_id=location_id, scale_type=scale_type).delete()
    LocationScaleRequirement.query.filter_by(location_id=location_id, scale_type=scale_type).delete()
    CoverageAcceptance.query.filter_by(location_id=location_id, scale_type=scale_type).delete()
    DoctorRoutine.query.filter_by(location_id=location_id, scale_type=scale_type).delete()


def sync_all_doctor_links():
    """Backfill: garante que todo médico tenha vínculo ativo com todo o universo atual."""
    for doc in User.query.filter_by(role='medico').all():
        link_doctor_to_all_positions(doc.id)
    db.session.commit()
