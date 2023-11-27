import string

from daras_ai_v2.crypto import get_random_string
from daras_ai_v2.vcard import VCARD, vard_img, vard_line, vard_escape

random_img1 = "https://picsum.photos/768"
random_img2 = "https://picsum.photos/1024"


def test_to_vcf_str():
    # Create a VCARD instance with sample data
    vcard = VCARD(
        format_name="John Doe",
        email="john@example.com",
        gender="male",
        birthday_year=1990,
        birthday_month=5,
        birthday_day=25,
        family_name="Doe",
        given_name="John",
        middle_names="Middle",
        honorific_prefixes=None,
        honorific_suffixes="Jr",
        impp="impp_value",
        address="123 Main St",
        calendar_url="http://example.com/calendar",
        comma_separated_categories="category1,category2",
        kind="individual",
        language="en",
        organization="Org",
        photo_url=random_img1,
        logo_url=random_img2,
        role="Role",
        timezone="UTC",
        job_title="Title",
        urls=["http://example.com/1", "http://example.com/2"],
        tel="123-456-7890",
        note="This is an unsually long note that doesn't make any sense. It just keeps going on and on without any real point or purpose. It's just a bunch of random words and thoughts thrown together.",
    )

    # Generate the VCF string
    vcf_str = vcard.to_vcf_str()

    # Check if the generated VCF string contains expected values
    assert vcf_str.startswith(
        """\
BEGIN:VCARD\r
VERSION:4.0\r
FN:John Doe\r
EMAIL:john@example.com\r
GENDER:male\r
BDAY:19900525\r
N:Doe;John;Middle;;Jr\r
IMPP:impp_value\r
ADR:123 Main St\r
CALURI:http\://example.com/calendar\r
CATEGORIES:category1\,category2\r
KIND:individual\r
LANG:en\r
ORG:Org\r
ROLE:Role\r
TZ:UTC\r
TITLE:Title\r
URL:http\://example.com/1\r
URL:http\://example.com/2\r
TEL;TYPE=cell:123-456-7890\r
NOTE:This is an unsually long note that doesn't make any sense. It just ke\r
 eps going on and on without any real point or purpose. It's just a bunch o\r
 f random words and thoughts thrown together.\r
"""
    )
    assert "PHOTO;" in vcf_str
    assert "LOGO;" in vcf_str
    assert vcf_str.endswith("END:VCARD")


def test_vard_img():
    # Test vard_img function with a sample image URL
    vard_img_str = vard_img("PHOTO", random_img1, compress_and_base64=True)

    # Check if the generated vCard image property is correctly formatted
    assert vard_img_str.startswith("PHOTO;ENCODING=BASE64;TYPE=PNG:")


def test_vard_line():
    # Test vard_line function with various inputs
    prop = "PROP"
    param1 = "Value1"
    param2 = get_random_string(1024, string.printable)
    param3 = "Value3"

    # Test with truncation enabled
    truncated_str = vard_line(prop, param1, param2, param3)
    for line in truncated_str.split():
        assert len(line) <= 75


def test_vard_escape():
    # Test vard_escape function with special characters
    text_with_special_chars = r"\,\:;\n\r"
    escaped_str = vard_escape(text_with_special_chars)

    # Check if the special characters are correctly escaped
    assert escaped_str == r"\\\,\\\:\;\\n\\r"
