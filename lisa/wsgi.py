from django.core.wsgi import get_wsgi_application

from lisa.settings._bootstrap import configure_settings_module

configure_settings_module()
application = get_wsgi_application()
