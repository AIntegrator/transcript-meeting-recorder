import os

from .base import *

DEBUG = True
# Allow overriding ALLOWED_HOSTS via environment variable (comma-separated). Keep sensible defaults.
_env_allowed = os.getenv("ALLOWED_HOSTS", "transcript-meeting-recorder-api,localhost")
ALLOWED_HOSTS = [h.strip() for h in _env_allowed.split(",") if h.strip()]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "attendee_development",
        "USER": "attendee_development_user",
        "PASSWORD": "attendee_development_user",
        "HOST": os.getenv("POSTGRES_HOST", "localhost"),
        "PORT": "5432",
    }
}

# Log more stuff in development
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "{asctime} - {name} - {levelname} - {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        # Uncomment to log database queries
        # "django.db.backends": {
        #    "handlers": ["console"],
        #    "level": "DEBUG",
        #    "propagate": False,
        # },
    },
}
