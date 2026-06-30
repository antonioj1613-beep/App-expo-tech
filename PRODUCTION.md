# Production deployment guide

This document records every change made to transform the demo Django project into a production-ready setup.

---

## Summary of changes

### 1. Dependencies (`requirements.txt`)

| Package | Purpose |
|---|---|
| `Django` | Web framework |
| `python-dotenv` | Load secrets from `.env` |
| `whitenoise` | Serve static files in production without nginx for assets |
| `gunicorn` | WSGI HTTP server for production |

### 2. Settings split (`lisa/settings/`)

Replaced the single `lisa/settings.py` with a modular package:

- **`base.py`** — shared config: apps, middleware, database, static files, logging, auth
- **`development.py`** — `DEBUG=True`, relaxed static storage, console email
- **`production.py`** — `DEBUG=False`, HTTPS security headers (HSTS, secure cookies, SSL redirect)

`manage.py` defaults to `lisa.settings.development`.  
`wsgi.py` / `asgi.py` default to `lisa.settings.production`.

### 3. Django apps & middleware

Added standard production apps:

- `django.contrib.admin`
- `django.contrib.auth`
- `django.contrib.contenttypes`
- `django.contrib.sessions`
- `django.contrib.messages`

Added full middleware stack including **CSRF**, **sessions**, **auth**, and **WhiteNoise**.

### 4. Database

- **Development default:** SQLite (`db.sqlite3`)
- **Production option:** set `DATABASE_URL=postgres://user:pass@host:5432/dbname`
- Ran all migrations (auth, admin, sessions, contenttypes, app)

### 5. Models (`app/models.py`)

| Model | Description |
|---|---|
| `UserProfile` | One-to-one with `User` — streak, XP, language prefs |
| `SkillProgress` | Per-skill level and progress per user |

Registered in Django admin with inline profile editing on the User admin page.

### 6. URL structure

- Moved route definitions to `app/urls.py`
- `lisa/urls.py` now mounts `/admin/` and includes `app.urls`

### 7. Static files

- `STATIC_ROOT = staticfiles/` for `collectstatic`
- WhiteNoise `CompressedManifestStaticFilesStorage` (production)
- `CompressedStaticFilesStorage` (development — no manifest required)

### 8. Security

| Setting | Development | Production |
|---|---|---|
| `SECRET_KEY` | from `.env` | from `.env` (must be strong) |
| `DEBUG` | `True` | `False` |
| `SECURE_SSL_REDIRECT` | off | on (configurable) |
| `SESSION_COOKIE_SECURE` | off | on |
| `CSRF_COOKIE_SECURE` | off | on |
| `SECURE_HSTS_SECONDS` | off | 31536000 |

### 9. Configuration files

- **`.env.example`** — template for environment variables
- **`.gitignore`** — excludes `.venv`, `db.sqlite3`, `.env`, `staticfiles/`

### 10. Logging

Structured console logging configured in `base.py` with `DJANGO_LOG_LEVEL` override.

---

## Deployment checklist

```bash
# 1. Clone / copy project
cd App-expo-tech

# 2. Virtual environment
python -m venv .venv
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# Windows Command Prompt:
# .venv\Scripts\activate.bat
# macOS/Linux:
# source .venv/bin/activate
pip install -r requirements.txt

# 3. Environment
cp .env.example .env
# Edit .env:
#   DJANGO_SECRET_KEY=<50+ random chars>
#   DJANGO_DEBUG=False
#   DJANGO_ALLOWED_HOSTS=yourdomain.com
#   DATABASE_URL=postgres://...

# 4. Database
export DJANGO_SETTINGS_MODULE=lisa.settings.production
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser

# 5. Run with Gunicorn
gunicorn lisa.wsgi:application --bind 0.0.0.0:8000 --workers 3
```

### Behind a reverse proxy (nginx)

Set in `.env`:

```
DJANGO_SECURE_SSL_REDIRECT=True
```

Ensure your proxy forwards `X-Forwarded-Proto: https`.

### Generate a secret key

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

---

## Verification performed

- `python manage.py check` — passed
- `python manage.py check --deploy` — warnings only in development (expected)
- `python manage.py migrate` — all migrations applied
- `python manage.py collectstatic` — 130 files collected
- `python manage.py runserver` — HTTP 200 on `/`

---

## What was intentionally unchanged

- All template views and demo data in `views.py` — UI works as before
- Frontend assets (Tailwind CDN, Lucide, Chart.js)
- No authentication wiring on login/register forms yet (models and admin are ready)

## Next recommended steps

1. Wire `login_view` / `register_view` to Django auth
2. Replace hardcoded dashboard data with `UserProfile` / `SkillProgress` queries
3. Add `pytest-django` and view tests
4. Add CI pipeline (lint, test, collectstatic check)
5. Use PostgreSQL in production via `DATABASE_URL`
