"""
Create a Twilio SIP trunk for a given phone number.

Usage:
    ./manage.py runscript create_twilio_sip_trunk --script-args PHONE_NUMBER
"""

from django.utils.text import slugify
from twilio.base.exceptions import TwilioException, TwilioRestException
from twilio.rest import Client
from asgiref.sync import async_to_sync
from daras_ai_v2 import settings


def run(phone_number: str) -> None:
    friendly_name = settings.LIVEKIT_SIP_TRUNK_NAME

    trunk = get_or_create_livekit_sip_inbound_trunk(friendly_name, phone_number)
    print(f"✅ {trunk=}")

    client = Client(
        account_sid=settings.TWILIO_ACCOUNT_SID,
        username=settings.TWILIO_API_KEY_SID,
        password=settings.TWILIO_API_KEY_SECRET,
    )

    incoming_phone_number = get_incoming_phone_number(client, phone_number)
    print(f"✅ {incoming_phone_number=}")

    trunk = get_or_create_trunk(client, friendly_name)
    print(f"✅ {trunk=}")

    origination_url = get_or_create_origination_url(
        client=client,
        trunk_sid=trunk.sid,
        sip_url=settings.LIVEKIT_SIP_URL,
        friendly_name=f"{friendly_name} Inbound",
    )
    print(f"✅ {origination_url=}")

    credential_list = get_or_create_credential_list(
        client=client,
        list_friendly_name=f"{friendly_name} Credentials",
    )
    print(f"✅ {credential_list=}")
    if not client.sip.credential_lists(credential_list.sid).credentials.list():
        credential = client.sip.credential_lists(
            credential_list.sid
        ).credentials.create(
            username=settings.LIVEKIT_SIP_TRUNK_USERNAME,
            password=settings.LIVEKIT_SIP_TRUNK_PASSWORD,
        )
        print(f"✅ {credential=}")

    attached_phone_number = attach_phone_number(
        client, trunk.sid, incoming_phone_number.sid
    )
    print(f"✅ {attached_phone_number=}")


@async_to_sync
async def get_or_create_livekit_sip_inbound_trunk(friendly_name, phone_number):
    from livekit import api

    livekit_api = api.LiveKitAPI()
    try:
        existing_trunks = await livekit_api.sip.list_sip_inbound_trunk(
            api.ListSIPInboundTrunkRequest(numbers=[phone_number])
        )
        if existing_trunks.items:
            return existing_trunks.items[0]

        return await livekit_api.sip.create_sip_inbound_trunk(
            api.CreateSIPInboundTrunkRequest(
                trunk=api.SIPInboundTrunkInfo(
                    name=slugify(friendly_name + " " + phone_number),
                    numbers=[phone_number],
                )
            )
        )
    finally:
        await livekit_api.aclose()


def get_incoming_phone_number(client: Client, phone_number: str):
    numbers = client.incoming_phone_numbers.list(phone_number=phone_number)
    if not numbers:
        raise ValueError(f"No incoming phone number found for {phone_number}")
    return numbers[0]


def get_or_create_trunk(client: Client, friendly_name: str):
    domain_name = slugify(friendly_name) + ".pstn.twilio.com"
    try:
        return client.trunking.v1.trunks.create(
            friendly_name=friendly_name,
            domain_name=domain_name,
        )
    except TwilioRestException as exc:
        if exc.code == 21248:
            trunks = client.trunking.v1.trunks.list()
            for trunk in trunks:
                trunk = trunk.fetch()
                if trunk.domain_name == domain_name:
                    return trunk
        raise


def get_or_create_origination_url(
    client: Client,
    trunk_sid: str,
    sip_url: str,
    friendly_name: str,
    priority: int = 1,
    weight: int = 1,
    enabled: bool = True,
):
    existing = client.trunking.v1.trunks(trunk_sid).origination_urls.list()
    for ou in existing:
        if ou.sip_url != sip_url:
            ou.delete()
    for ou in existing:
        if ou.sip_url == sip_url:
            return ou
    return client.trunking.v1.trunks(trunk_sid).origination_urls.create(
        sip_url=sip_url,
        friendly_name=friendly_name,
        priority=priority,
        weight=weight,
        enabled=enabled,
    )


def get_or_create_credential_list(
    client: Client,
    list_friendly_name: str,
):
    try:
        return client.sip.credential_lists.create(friendly_name=list_friendly_name)
    except TwilioException as exc:
        if exc.code == 21240:
            clists = client.sip.credential_lists.list()
            for cl in clists:
                if cl.friendly_name == list_friendly_name:
                    return cl
        raise


def attach_phone_number(client: Client, trunk_sid: str, phone_number_sid: str):
    return client.trunking.v1.trunks(trunk_sid).phone_numbers.create(
        phone_number_sid=phone_number_sid
    )
