from flask_login import current_user
from app.extensions import db
from app.models.audit import AuditLog


def log(action, entity_type=None, entity_id=None, details=None):
    user_id = current_user.id if current_user and current_user.is_authenticated else None
    entry = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
    )
    db.session.add(entry)
