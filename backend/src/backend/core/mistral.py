from mistralai.client import Mistral
from mistralai.client.utils import BackoffStrategy, RetryConfig

from backend.core.config import get_settings


def create_mistral_client() -> Mistral:
    return Mistral(
        api_key=get_settings().mistral_api_key,
        # Retries 429 and 5xx responses and connection errors with exponential
        # backoff, for up to 2 minutes per request.
        retry_config=RetryConfig(
            "backoff",
            BackoffStrategy(
                initial_interval=1_000,
                max_interval=30_000,
                exponent=2,
                max_elapsed_time=120_000,
            ),
            retry_connection_errors=True,
        ),
    )
