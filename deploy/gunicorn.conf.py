bind = "127.0.0.1:8000"
workers = 3
worker_class = "sync"
timeout = 120
accesslog = "/var/log/escala/gunicorn_access.log"
errorlog  = "/var/log/escala/gunicorn_error.log"
loglevel  = "info"
