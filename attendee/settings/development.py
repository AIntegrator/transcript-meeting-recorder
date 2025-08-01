import os

from .base import *

DEBUG = True
ALLOWED_HOSTS = ["localhost"]

additional_hosts = os.getenv("ALLOWED_HOSTS")

# If the environment variable exists, split it by comma and add to the list
if additional_hosts:
    # We use a list comprehension to strip any whitespace from each host
    ALLOWED_HOSTS.extend([host.strip() for host in additional_hosts.split(',')])


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
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
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
    },
}
