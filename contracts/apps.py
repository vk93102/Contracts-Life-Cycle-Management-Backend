from django.apps import AppConfig


class ContractsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'contracts'
    
    def ready(self):
        """
        Import signals when Django starts
        This activates the Observer Pattern listeners
        """
        try:
            import contracts.workflow_signals  # noqa
        except ImportError:
            pass
