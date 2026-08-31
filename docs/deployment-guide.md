# Deployment Guide

Production stack:

- Ubuntu/Linux VPS
- Nginx
- Gunicorn
- MySQL 8+
- Redis
- Celery
- Celery Beat
- HTTPS

Checklist:

1. Create a production `.env` from `.env.example`.
2. Set `DJANGO_DEBUG=False`.
3. Use a long random `DJANGO_SECRET_KEY`.
4. Set exact `DJANGO_ALLOWED_HOSTS`.
5. Configure MySQL and Redis.
6. Run migrations.
7. Run `collectstatic`.
8. Run Gunicorn under systemd.
9. Run Celery and Celery Beat under systemd.
10. Configure Nginx reverse proxy, static, media, and HTTPS.
11. Configure backups and monitoring.
