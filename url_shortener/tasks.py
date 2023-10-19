import requests
import user_agents
from furl import furl

from celeryapp import app
from url_shortener.models import VisitorClickInfo


@app.task
def save_click_info(surl_id: int, ip_address: str, user_agent: str):
    if user_agent:
        ua_data = user_agents.parse(user_agent)
        browser = ua_data.browser._asdict()
        device = ua_data.device._asdict()
        os = ua_data.os._asdict()
    else:
        browser = None
        device = None
        os = None

    res = requests.get(str(furl("https://iplist.cc/api/") / ip_address))
    if res.ok:
        ip_data = res.json()
    else:
        ip_data = {}

    VisitorClickInfo.objects.create(
        shortened_url_id=surl_id,
        ip_address=ip_address,
        user_agent=user_agent,
        browser=browser,
        device=device,
        os=os,
        ip_data=ip_data,
    )
