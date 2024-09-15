import random

import requests
from furl import furl

from daras_ai_v2 import settings
from daras_ai_v2.fake_user_agents import FAKE_USER_AGENTS

if settings.SCRAPING_PROXY_HOST:
    SCRAPING_PROXIES = {
        scheme: str(
            furl(
                scheme="http",
                host=settings.SCRAPING_PROXY_HOST,
                username=settings.SCRAPING_PROXY_USERNAME,
                password=settings.SCRAPING_PROXY_PASSWORD,
            ),
        )
        for scheme in ["http", "https"]
    }
else:
    SCRAPING_PROXIES = {}


def get_scraping_proxy_cert_path() -> str | None:
    if not settings.SCRAPING_PROXY_CERT_URL:
        return None

    path = settings.BASE_DIR / "proxy_ca_crt.pem"
    if not path.exists():
        settings.logger.info(f"Downloading proxy cert to {path}")
        path.write_bytes(requests.get(settings.SCRAPING_PROXY_CERT_URL).content)

    return str(path)


def requests_scraping_kwargs() -> dict:
    """Return kwargs for requests library to use scraping proxy and fake user agent."""
    return dict(
        headers={"User-Agent": random.choice(FAKE_USER_AGENTS)},
        proxies=SCRAPING_PROXIES,
        verify=get_scraping_proxy_cert_path(),
        # verify=False,
    )
