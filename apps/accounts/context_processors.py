from django.conf import settings


def registration_status(request):
    """Expose registration status to templates."""
    return {
        "REGISTRATION_ENABLED": getattr(settings, "REGISTRATION_ENABLED", True),
    }
