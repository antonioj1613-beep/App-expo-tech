from django.core.wsgi import get_wsgi_application

from lisa.settings._bootstrap import configure_settings_module

configure_settings_module()
application = get_wsgi_application()

from lisa.serverless_boot import ensure_serverless_database  # noqa: E402

ensure_serverless_database()

# Vercel Python runtime may look for `app`
app = application
