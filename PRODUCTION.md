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
- **Vercel / production (required for real accounts):** set `DATABASE_URL` to Postgres
  - Neon free: https://neon.tech → create project → copy connection string
  - Must include `?sslmode=require` (or the app adds it automatically on serverless)
  - Add as a Vercel Environment Variable for **Production** and **Preview**, then redeploy
  - Without this, the app uses ephemeral `/tmp` SQLite and accounts appear to “delete” themselves
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
- WhiteNoise `CompressedStaticFilesStorage` (Vercel-safe; Manifest storage breaks collectstatic on Vercel)
- CDN serves collected static on Vercel

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

### A. Before you deploy (local)

- [ ] `python manage.py check` passes
- [ ] `python manage.py migrate` applies cleanly
- [ ] `python manage.py seed_skills` (and lesson seeds if needed) run without errors
- [ ] Local smoke test with `.\start.ps1`: `/`, `/login/`, `/register/`, `/levels/` return 200
- [ ] No secrets committed (`.env` is in `.gitignore`)

### B. Vercel project settings (one-time)

**Environment variables** (Production + Preview):

| Variable | Required value |
|---|---|
| `DJANGO_SETTINGS_MODULE` | `lisa.settings.production` |
| `DJANGO_DEBUG` | `False` |
| `DJANGO_SECRET_KEY` | Long random string (never the example key) |
| `DJANGO_ALLOWED_HOSTS` | `*` (or your domains) |
| `DATABASE_URL` | **Required for persistent accounts** — Postgres URL (Neon/Supabase/Vercel Postgres) |

#### Postgres setup (Neon — free, ~5 minutes)

1. Sign up at [neon.tech](https://neon.tech) and create a project.
2. Dashboard → **Connection string** → copy the URI (starts with `postgresql://…`).
3. Vercel → Project → **Settings → Environment Variables** → add:
   - Name: `DATABASE_URL`
   - Value: paste the Neon URI
   - Environments: Production + Preview
4. Redeploy the project (Deployments → ⋯ → Redeploy).
5. First request runs migrations against Postgres automatically (`serverless_boot`).
6. Register a new account and navigate Profile → Dashboard — you should stay logged in.

Optional: leave `DJANGO_ALLOWED_HOSTS` unset — code already allows all hosts on Vercel.

**Deployment Protection (critical for public links):**

- [ ] **Settings → Deployment Protection → Vercel Authentication → Disabled**  
  (or Standard Protection that leaves **Production** public)
- [ ] Confirm strangers are not sent to “Log in to Vercel”

**Share only the Production domain:**

- Good: `https://app-expo-tech-learning-skills.vercel.app`
- Bad (often gated): `https://app-expo-tech-<hash>-learning-skills.vercel.app` (Preview)

### C. After each deploy (must pass)

Run these against the **Production** URL (incognito / second device):

| # | Check | Expected |
|---|---|---|
| 1 | Open `/` | Landing page loads (HTTP **200**, not 500 / DisallowedHost) |
| 2 | Open site while logged out of Vercel | **No** Vercel login screen |
| 3 | `/favicon.ico` | Redirect or icon (not a broken app 500) |
| 4 | `/static/app/theme.css` | CSS loads (200 / CDN) |
| 5 | `/register/` → create account | Account created; lands on dashboard |
| 6 | `/login/` | Sign-in works |
| 7 | `/levels/` | Level cards for Listening / Reading / Writing / Vocabulary |
| 8 | `/reading/` → answer → submit | Quiz works; XP updates |
| 9 | `/listening/` → submit | Quiz works |
| 10 | `/speaking/` | UI loads (full Vosk/Ollama tutor may be limited on Vercel) |
| 11 | `/dashboard/`, `/progress/`, `/statistics/` | Pages render without 500 |
| 12 | Hard refresh / second laptop | Same Production URL works without Vercel auth |

### D. Build / runtime failures (common)

| Symptom | Fix |
|---|---|
| `DisallowedHost` | Deploy includes `ALLOWED_HOSTS = ["*"]`; set `DJANGO_SETTINGS_MODULE=lisa.settings.production` |
| `ENOENT ... staticfiles.json` | Use `CompressedStaticFilesStorage` (not Manifest) on Vercel |
| HTTP **500** on `/` | Cold-start migrate to `/tmp` SQLite; check Runtime Logs |
| Vercel login wall for visitors | Disable Deployment Protection; share **Production** domain only |
| Data resets after idle / kicked to login from Profile | Missing or invalid `DATABASE_URL` — add Neon/Postgres and redeploy |
| Speaking transcription fails | Expected on serverless without Vosk/Ollama — use local `.\start.ps1` for full voice AI |

### E. Promote a known-good build

1. Vercel → **Deployments** → open a deployment that passed section C
2. **⋯ → Promote to Production** (if it is only a Preview)
3. Copy the domain from **Settings → Domains**
4. Retest section C on that domain in incognito

### F. Self-hosted / VPS (non-Vercel)

```bash
cd App-expo-tech
python -m venv .venv
# Windows: .\.venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env: DJANGO_SECRET_KEY, DJANGO_DEBUG=False, hosts, DATABASE_URL
export DJANGO_SETTINGS_MODULE=lisa.settings.production
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py seed_skills
python manage.py createsuperuser
gunicorn lisa.wsgi:application --bind 0.0.0.0:8000 --workers 3
```

Behind nginx, set `DJANGO_SECURE_SSL_REDIRECT=True` and forward `X-Forwarded-Proto: https`.

### Generate a secret key

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

---

## Verification performed

- `python manage.py check` — passed
- `python manage.py check --deploy` — warnings only in development (expected)
- `python manage.py migrate` — all migrations applied
- `python manage.py collectstatic` — static files collected
- `python manage.py runserver` — HTTP 200 on `/`
- Vercel: production URL reachable with Deployment Protection disabled for public demos

---

## What was intentionally unchanged

- Frontend assets (Tailwind CDN, Lucide, Chart.js)
- Hybrid content model (seed commands + staff lesson builder)

## Next recommended steps

1. ~~Add PostgreSQL on Vercel (`DATABASE_URL`) so accounts/progress persist~~ → see section B (Neon)
2. Add CI: `manage.py check`, migrate dry-run, and a smoke HTTP check on `/`
3. Document Speaking limits on serverless vs local Ollama/Vosk
4. Optional custom domain in Vercel → Domains (not required for public demos)
