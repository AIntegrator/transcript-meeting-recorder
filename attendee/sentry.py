import logging
import sentry_sdk
from django.conf import settings
from sentry_sdk.integrations.django import DjangoIntegration

logger = logging.getLogger(__name__)


def init_sentry():
    # Initialize Sentry only if enabled (disabled by default for local development)
    if settings.DISABLE_SENTRY is False:
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            send_default_pii=True,

            # By setting this option, Sentry will capture information about Django requests
            integrations=[
                DjangoIntegration(),
            ],
        )
        logger.info("Sentry error tracking initialized")
    else:
        logger.info("Sentry error tracking disabled")