import requests
from furl import furl

from daras_ai_v2 import settings
from daras_ai_v2.exceptions import raise_for_status
from routers.paypal import generate_auth_header


def run(base_url: str = None):
    base_url = base_url or settings.APP_BASE_URL
    response = requests.post(
        str(furl(settings.PAYPAL_BASE) / "v1/notifications/webhooks"),
        headers={"Authorization": generate_auth_header()},
        json={
            "url": str(furl(base_url) / "__/paypal/webhook/"),
            "event_types": [
                {
                    "name": "PAYMENT.SALE.COMPLETED",
                },
            ],
        },
    )
    raise_for_status(response)
    print(response.json())
