"""Gunicorn for MHRS on the shared VPS: threaded workers (ADR-029), loopback only."""

bind = "127.0.0.1:8400"
worker_class = "gthread"
workers = 2
threads = 4
timeout = 60
graceful_timeout = 30
keepalive = 5
max_requests = 2000
max_requests_jitter = 200
forwarded_allow_ips = "127.0.0.1"
accesslog = "-"
errorlog = "-"
