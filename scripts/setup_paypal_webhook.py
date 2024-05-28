import requests
from furl import furl

from daras_ai_v2 import paypal, settings
from daras_ai_v2.exceptions import raise_for_status


def run(base_url: str = settings.APP_BASE_URL):
    response = requests.post(
        str(furl(settings.PAYPAL_BASE) / "v1/notifications/webhooks"),
        headers={"Authorization": paypal.generate_auth_header()},
        json={
            "url": str(furl(base_url) / "__/paypal/webhook/"),
            "event_types": [
                {
                    "name": "PAYMENT.SALE.COMPLETED",
                },
                {
                    "name": "BILLING.SUBSCRIPTION.ACTIVATED",
                },
                {
                    "name": "BILLING.SUBSCRIPTION.UPDATED",
                },
                {
                    "name": "BILLING.SUBSCRIPTION.CANCELLED",
                },
                {
                    "name": "BILLING.SUBSCRIPTION.EXPIRED",
                },
            ],
        },
    )
    raise_for_status(response)
    print(response.json())
