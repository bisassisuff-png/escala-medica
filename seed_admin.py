"""
Cria o primeiro usuário ADMIN no banco de dados.
Uso: python seed_admin.py
"""
import os
from app import create_app
from app.extensions import db
from app.models.user import User

app = create_app()

with app.app_context():
    login = os.environ.get('ADMIN_LOGIN', 'admin')
    email = os.environ.get('ADMIN_EMAIL', 'admin@escalamedica.local')
    password = os.environ.get('ADMIN_PASSWORD', 'admin123')

    existing = User.query.filter_by(login=login).first()
    if existing:
        print(f'Admin "{login}" já existe.')
    else:
        admin = User(
            name='Administrador',
            login=login,
            email=email,
            role='admin',
        )
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()
        print(f'Admin criado: login={login}, senha={password}')
        print('ATENÇÃO: troque a senha após o primeiro login.')
