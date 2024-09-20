import requests
from furl import furl

from celeryapp import app
from daras_ai_v2.exceptions import raise_for_status
from url_shortener.models import VisitorClickInfo


@app.task
def save_click_info(surl_id: int, ip_address: str, user_agent: str):
    import user_agents

    if user_agent:
        ua_data = user_agents.parse(user_agent)
        browser = ua_data.browser._asdict()
        device = ua_data.device._asdict()
        os = ua_data.os._asdict()
    else:
        browser = None
        device = None
        os = None

    ip_data = {}
    try:
        res = requests.get(
            str(furl("http://ip-api.com/json") / ip_address),
        )
        raise_for_status(res)
        ip_data = res.json()
        if ip_data.get("status") == "success":
            ip_data.pop("status")  # remove success status
        ip_data.pop("query", None)  # remove the query ip
    finally:
        # save the visitor click info irregarless of the IP data being fetched
        VisitorClickInfo.objects.create(
            shortened_url_id=surl_id,
            ip_address=ip_address,
            user_agent=user_agent,
            browser=browser,
            device=device,
            os=os,
            ip_data=ip_data,
        )
