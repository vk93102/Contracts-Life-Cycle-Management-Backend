"""
CLM Backend initialization
Loads Celery app so it's available when Django starts
"""
try:
	from .celery import app as celery_app

	__all__ = ('celery_app',)
except Exception:
	celery_app = None
	__all__ = ()
