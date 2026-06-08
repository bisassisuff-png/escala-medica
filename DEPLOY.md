# Deploy em VPS — Escala Médica

Stack: **Python 3.12 · Flask · PostgreSQL 16 · Gunicorn · Nginx · Supervisor**

---

## 1. Preparação da VPS

```bash
# Ubuntu 22.04 / 24.04
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.12 python3.12-venv python3-pip postgresql postgresql-contrib nginx supervisor git
```

---

## 2. Banco de Dados

```bash
sudo -u postgres psql
```
```sql
CREATE USER escala WITH PASSWORD 'TROQUE_ESTA_SENHA';
CREATE DATABASE escala_medica OWNER escala;
GRANT ALL PRIVILEGES ON DATABASE escala_medica TO escala;
\q
```

---

## 3. Aplicação

```bash
# Criar usuário de sistema
sudo useradd -m -s /bin/bash escala
sudo su - escala

# Clonar repositório
git clone <URL_DO_REPO> /home/escala/app
cd /home/escala/app

# Virtualenv e dependências
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install gunicorn

# Configurar ambiente
cp .env.example .env
nano .env
```

### .env (produção)

```env
FLASK_ENV=production
SECRET_KEY=<GERE_COM: python3 -c "import secrets; print(secrets.token_hex(32))">
DATABASE_URL=postgresql://escala:TROQUE_ESTA_SENHA@localhost:5432/escala_medica
```

### Migrations e seed

```bash
.venv/bin/flask db upgrade
python seed_admin.py
# Anote a senha gerada — é o único acesso admin inicial
```

---

## 4. Gunicorn

Crie `/home/escala/app/deploy/gunicorn.conf.py`:

```python
bind = "127.0.0.1:8000"
workers = 3          # Regra geral: 2 × núcleos + 1
worker_class = "sync"
timeout = 120
accesslog = "/var/log/escala/gunicorn_access.log"
errorlog  = "/var/log/escala/gunicorn_error.log"
loglevel  = "info"
```

```bash
sudo mkdir -p /var/log/escala
sudo chown escala:escala /var/log/escala
```

**Testar antes de configurar Supervisor:**
```bash
.venv/bin/gunicorn -c deploy/gunicorn.conf.py "run:app"
# Acesse http://IP:8000 para verificar
# Ctrl+C para parar
```

---

## 5. Supervisor

Crie `/etc/supervisor/conf.d/escala.conf`:

```ini
[program:escala]
command=/home/escala/app/.venv/bin/gunicorn -c /home/escala/app/deploy/gunicorn.conf.py "run:app"
directory=/home/escala/app
user=escala
autostart=true
autorestart=true
stopasgroup=true
killasgroup=true
stderr_logfile=/var/log/escala/supervisor_err.log
stdout_logfile=/var/log/escala/supervisor_out.log
environment=FLASK_ENV="production"
```

```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start escala
sudo supervisorctl status escala
```

---

## 6. Nginx

Crie `/etc/nginx/sites-available/escala`:

```nginx
server {
    listen 80;
    server_name SEU_DOMINIO.com www.SEU_DOMINIO.com;

    # Redirecionar para HTTPS (ativar após configurar SSL)
    # return 301 https://$host$request_uri;

    location /static/ {
        alias /home/escala/app/app/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
        proxy_connect_timeout 10s;
        client_max_body_size 16M;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/escala /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## 7. SSL (Let's Encrypt)

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d SEU_DOMINIO.com -d www.SEU_DOMINIO.com
# Certbot modifica o nginx.conf automaticamente para HTTPS + redirect
sudo systemctl reload nginx
```

---

## 8. Operação

### Atualizar a aplicação

```bash
sudo su - escala
cd /home/escala/app
git pull
.venv/bin/pip install -r requirements.txt  # se requirements mudou
.venv/bin/flask db upgrade                  # se há novas migrations
exit
sudo supervisorctl restart escala
```

### Logs

```bash
# Logs da aplicação (gunicorn)
tail -f /var/log/escala/gunicorn_error.log

# Logs do supervisor
sudo supervisorctl tail -f escala stderr

# Logs do nginx
tail -f /var/log/nginx/error.log
```

### Status dos serviços

```bash
sudo supervisorctl status escala
sudo systemctl status nginx
sudo systemctl status postgresql
```

### Backup do banco

```bash
sudo -u postgres pg_dump escala_medica | gzip > /tmp/escala_$(date +%Y%m%d).sql.gz
```

---

## 9. Variáveis de Ambiente em Produção

| Variável | Descrição |
|---|---|
| `SECRET_KEY` | Chave aleatória segura (hex 32 bytes) |
| `DATABASE_URL` | URL completa do PostgreSQL |
| `FLASK_ENV` | Deve ser `production` |

> **Nunca** comite o `.env` de produção no repositório.

---

## 10. Firewall (UFW)

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
sudo ufw status
```

O gunicorn escuta apenas em `127.0.0.1:8000` (não exposto diretamente).

---

## Verificação Final

```bash
# App responde?
curl -I http://SEU_DOMINIO.com/login

# HTTPS funciona?
curl -I https://SEU_DOMINIO.com/login

# Banco conecta?
sudo su - escala
cd app && .venv/bin/flask shell
>>> from app.extensions import db
>>> db.session.execute(db.text('SELECT 1')).scalar()
1
```
