# InfoSaas

Production-grade multi-tenant news SaaS built with Django.

## Runtime

- Python 3.14.7 or newer
- Django 5.2.8+ LTS
- MySQL 8+ for production
- Redis for Celery and background jobs

The machine `python` currently points to Python 3.7, which is too old for Django 5.2. Install Python 3.14.7+, then recreate the virtual environment.

## Setup

```powershell
python --version
python -m venv .venv314
.\.venv314\Scripts\python.exe -m pip install --upgrade pip
.\.venv314\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv314\Scripts\python.exe manage.py migrate
.\.venv314\Scripts\python.exe manage.py test
```

For local development without MySQL variables in `.env`, the project uses SQLite. Set `MYSQL_DATABASE`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_HOST`, and `MYSQL_PORT` for MySQL.

## Phase Status

Phase 1 is complete:

- Custom user model
- Tenant and tenant membership models
- Tenant domain foundation
- Host-based tenant resolution middleware
- Tenant-aware query/form/view helpers
- Audit log foundation
- SaaS admin and tenant dashboard foundations
- Tenant isolation tests
