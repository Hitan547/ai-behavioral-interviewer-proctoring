"""
sentry_setup.py
---------------
Centralized Sentry initialization for PsySense.
Import this module early in any entrypoint (demo_app.py, microservice main.py)
to enable automatic exception tracking.

If SENTRY_DSN is not set, Sentry is silently disabled — zero side-effects.
"""

import os

_initialized = False


def init_sentry():
    """Initialize Sentry SDK if SENTRY_DSN is configured.

    Safe to call multiple times — only initializes once.
    Works with both Streamlit and FastAPI.
    """
    global _initialized
    if _initialized:
        return

    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        return

    try:
        import sentry_sdk

        environment = os.getenv("ENVIRONMENT", "development").strip().lower()

        sentry_sdk.init(
            dsn=dsn,
            environment=environment,
            traces_sample_rate=0.2 if environment == "production" else 1.0,
            profiles_sample_rate=0.1,
            send_default_pii=False,  # don't send user IPs/emails to Sentry
            attach_stacktrace=True,
        )

        _initialized = True
        print(f"[sentry] Initialized for {environment} environment", flush=True)

    except ImportError:
        print("[sentry] sentry-sdk not installed — monitoring disabled", flush=True)
    except Exception as e:
        print(f"[sentry] Init failed: {e}", flush=True)


# Auto-initialize on import
init_sentry()
