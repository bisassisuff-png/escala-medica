import os
from dotenv import load_dotenv

load_dotenv()

# Raiz do projeto (config.py fica na raiz) — para ancorar caminhos absolutos.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-key-insegura')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = True

    # Limite de tamanho por requisição (chunks de áudio são pequenos; ~1s de webm/opus).
    # Protege o endpoint de upload de chunks contra abuso. 10 MB é folgado por chunk.
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', 10 * 1024 * 1024))

    # Diretório das gravações de reunião — FORA de qualquer pasta estática/pública.
    # Nunca deve ser servível por URL. Permissão 700 (ver passos de deploy).
    GRAVACOES_DIR = os.environ.get('GRAVACOES_DIR', os.path.join(BASE_DIR, 'gravacoes'))

    # Feature flag do módulo de reuniões. Default desligado: o item aparece no menu
    # (desativado) e as rotas ficam bloqueadas. Para ligar: REUNIOES_ENABLED=true no .env.
    REUNIOES_ENABLED = os.environ.get('REUNIOES_ENABLED', 'false').strip().lower() in ('1', 'true', 'yes', 'on')

    # LiveKit (videochamada ao vivo) e DeepSeek (geração de ata) — segredos via .env.
    LIVEKIT_API_KEY = os.environ.get('LIVEKIT_API_KEY')
    LIVEKIT_API_SECRET = os.environ.get('LIVEKIT_API_SECRET')
    LIVEKIT_WS_URL = os.environ.get('LIVEKIT_WS_URL')
    DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/escala_medica'
    )


class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')


class TestingConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    REUNIOES_ENABLED = True  # testes funcionais do módulo rodam com a flag ligada
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'TEST_DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/escala_medica_test'
    )


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig,
}
