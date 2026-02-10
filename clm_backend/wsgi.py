"""
WSGI config for clm_backend project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

from clm_backend.otel import init_otel

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'clm_backend.settings')

init_otel()

application = get_wsgi_application()
