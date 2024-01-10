import base64
import time

import requests
from pydantic import BaseModel

from daras_ai.image_input import resize_img_scale
from daras_ai_v2.exceptions import raise_for_status

# see - https://datatracker.ietf.org/doc/html/rfc6350#section-3.2
CRLF = "\r\n"
LINEBREAK = "\r\n" + " "
MAXWIDTH = 75


class VCARD(BaseModel):
    format_name: str
    email: str | None
    gender: str | None
    birthday_year: int | None
    birthday_month: int | None
    birthday_day: int | None
    family_name: str | None
    given_name: str | None
    middle_names: str | None
    honorific_prefixes: str | None
    honorific_suffixes: str | None
    impp: str | None
    address: str | None
    calendar_url: str | None
    comma_separated_categories: str | None
    kind: str | None
    language: str | None
    organization: str | None
    photo_url: str | None
    logo_url: str | None
    role: str | None
    timezone: str | None
    job_title: str | None
    urls: list[str] | None
    tel: str | None
    note: str | None

    def to_vcf_str(self, compress_and_base64: bool = True) -> str:
        if not self.format_name:
            raise ValueError("Please provide a name")
        lines = [
            vard_line("FN", self.format_name),
        ]
        if self.email:
            lines.append(vard_line("EMAIL", self.email))
        if self.gender:
            lines.append(vard_line("GENDER", self.gender))
        if self.birthday_year or self.birthday_month or self.birthday_day:
            bday = (
                str(self.birthday_year or "--").rjust(4, "0")
                + str(self.birthday_month or "--").rjust(2, "0")
                + str(self.birthday_day or "--").rjust(2, "0")
            )
            lines.append(vard_line("BDAY", bday))
        names = [
            self.family_name,
            self.given_name,
            self.middle_names,
            self.honorific_prefixes,
            self.honorific_suffixes,
        ]
        if any(names):
            lines.append(vard_line("N", *[(n or "") for n in names]))
        if self.impp:
            lines.append(vard_line("IMPP", self.impp))
        if self.address:
            lines.append(vard_line("ADR", self.address))
        if self.calendar_url:
            lines.append(vard_line("CALURI", self.calendar_url))
        if self.comma_separated_categories:
            lines.append(vard_line("CATEGORIES", self.comma_separated_categories))
        if self.kind:
            lines.append(vard_line("KIND", self.kind))
        else:
            lines.append(vard_line("KIND", "individual"))
        if self.language:
            lines.append(vard_line("LANG", self.language))
        if self.organization:
            lines.append(vard_line("ORG", self.organization))
        if self.role:
            lines.append(vard_line("ROLE", self.role))
        if self.timezone:
            lines.append(vard_line("TZ", self.timezone))
        if self.job_title:
            lines.append(vard_line("TITLE", self.job_title))
        if self.urls:
            for url in self.urls:
                lines.append(vard_line("URL", url))
        if self.tel:
            lines.append(vard_line("TEL;TYPE=cell", self.tel))
        if self.note:
            lines.append(vard_line("NOTE", self.note))
        if self.photo_url:
            lines.append(vard_img("PHOTO", self.photo_url, compress_and_base64))
        if self.logo_url:
            lines.append(vard_img("LOGO", self.logo_url, compress_and_base64))
        return CRLF.join(
            [
                "BEGIN:VCARD",
                "VERSION:4.0",
                *lines,
                ## this tends to generate a new file every time, not sure if it's useful?
                # f"REV:{int(time.time() * 1000)}",
                "PRODID:-//GooeyAI//NONSGML Gooey vCard V1.0//EN",
                "END:VCARD",
            ]
        )


def vard_img(prop: str, img: str, compress_and_base64: bool, fmt: str = "PNG") -> str:
    if compress_and_base64:
        r = requests.get(img)
        raise_for_status(r)
        downscaled = resize_img_scale(r.content, (400, 400))
        img = base64.b64encode(downscaled).decode()
    return prop + ";" + vard_line(f"ENCODING=BASE64;TYPE={fmt}", img)


def vard_line(prop: str, *params: str) -> str:
    ret = prop + ":" + ";".join(map(vard_escape, params))
    if len(ret) > MAXWIDTH:
        ret = LINEBREAK.join(
            ret[i : i + MAXWIDTH - 1] for i in range(0, len(ret), MAXWIDTH - 1)
        )
    return ret


def vard_escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(",", "\\,")
        .replace(":", "\\:")
        .replace(";", "\\;")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )
