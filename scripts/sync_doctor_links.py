"""Garante que todo médico ativo tenha vínculo ativo com todas as posições
(local + tipo de escala) já conhecidas no sistema. Roda uma vez para corrigir
vínculos faltantes em bases existentes (premissa "todos vinculados a tudo").
"""
from app import create_app
from app.services.location_service import sync_all_doctor_links

app = create_app()
with app.app_context():
    sync_all_doctor_links()
    print("Vínculos sincronizados.")
