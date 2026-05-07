from django.apps import AppConfig


class LabConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "lab"
    verbose_name = "Laboratorio"

    def ready(self):
        import os
        if os.environ.get("RUN_MAIN") != "true":
            return
        from .engine import start_scheduler
        start_scheduler()
