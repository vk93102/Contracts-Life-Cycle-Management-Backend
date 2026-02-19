import os

from django.core.wsgi import get_wsgi_application

from clm_backend.otel import init_otel

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'clm_backend.settings')

init_otel()

application = get_wsgi_application()
