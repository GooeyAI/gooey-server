from django.db.models import TextChoices
from pydantic import BaseModel
from pydantic import Field

import gooey_ui as st


def serp_search_settings():
    st.write("#### Web Search Tools\n(via [serper.dev](https://serper.dev/))")

    col1, col2 = st.columns(2)
    with col1:
        serp_search_type_selectbox()
    with col2:
        serp_search_location_selectbox()
    st.number_input(
        label="""
        ###### Max Search URLs
        The maximum number of search URLs to consider as References
        """,
        key="max_search_urls",
        min_value=1,
        max_value=10,
    )


def serp_search_type_selectbox(key="serp_search_type"):
    st.selectbox(
        f"###### {GoogleSearchMixin.__fields__[key].field_info.title}\n{GoogleSearchMixin.__fields__[key].field_info.description or ''}",
        options=SerpSearchType,
        format_func=lambda x: x.label,
        key=key,
    )


def serp_search_location_selectbox(key="serp_search_location"):
    st.selectbox(
        f"###### {GoogleSearchMixin.__fields__[key].field_info.title}\n{GoogleSearchMixin.__fields__[key].field_info.description or ''}",
        options=SerpSearchLocation,
        format_func=lambda x: f"{x.label} ({x.value})",
        key=key,
        default_value=SerpSearchLocation.UNITED_STATES,
    )


class SerpSearchType(TextChoices):
    SEARCH = "search", "🔎 Search"
    IMAGES = "images", "📷 Images"
    VIDEOS = "videos", "🎥 Videos"
    PLACES = "places", "📍 Places"
    NEWS = "news", "📰 News"


class SerpSearchLocation(TextChoices):
    AFGHANISTAN = "af", "Afghanistan"
    ALBANIA = "al", "Albania"
    ALGERIA = "dz", "Algeria"
    AMERICAN_SAMOA = "as", "American Samoa"
    ANDORRA = "ad", "Andorra"
    ANGOLA = "ao", "Angola"
    ANGUILLA = "ai", "Anguilla"
    ANTARCTICA = "aq", "Antarctica"
    ANTIGUA_AND_BARBUDA = "ag", "Antigua and Barbuda"
    ARGENTINA = "ar", "Argentina"
    ARMENIA = "am", "Armenia"
    ARUBA = "aw", "Aruba"
    AUSTRALIA = "au", "Australia"
    AUSTRIA = "at", "Austria"
    AZERBAIJAN = "az", "Azerbaijan"
    BAHAMAS = "bs", "Bahamas"
    BAHRAIN = "bh", "Bahrain"
    BANGLADESH = "bd", "Bangladesh"
    BARBADOS = "bb", "Barbados"
    BELARUS = "by", "Belarus"
    BELGIUM = "be", "Belgium"
    BELIZE = "bz", "Belize"
    BENIN = "bj", "Benin"
    BERMUDA = "bm", "Bermuda"
    BHUTAN = "bt", "Bhutan"
    BOLIVIA = "bo", "Bolivia"
    BOSNIA_AND_HERZEGOVINA = "ba", "Bosnia and Herzegovina"
    BOTSWANA = "bw", "Botswana"
    BOUVET_ISLAND = "bv", "Bouvet Island"
    BRAZIL = "br", "Brazil"
    BRITISH_INDIAN_OCEAN_TERRITORY = "io", "British Indian Ocean Territory"
    BRUNEI_DARUSSALAM = "bn", "Brunei Darussalam"
    BULGARIA = "bg", "Bulgaria"
    BURKINA_FASO = "bf", "Burkina Faso"
    BURUNDI = "bi", "Burundi"
    CAMBODIA = "kh", "Cambodia"
    CAMEROON = "cm", "Cameroon"
    CANADA = "ca", "Canada"
    CAPE_VERDE = "cv", "Cape Verde"
    CAYMAN_ISLANDS = "ky", "Cayman Islands"
    CENTRAL_AFRICAN_REPUBLIC = "cf", "Central African Republic"
    CHAD = "td", "Chad"
    CHILE = "cl", "Chile"
    CHINA = "cn", "China"
    CHRISTMAS_ISLAND = "cx", "Christmas Island"
    COCOS_KEELING_ISLANDS = "cc", "Cocos (Keeling) Islands"
    COLOMBIA = "co", "Colombia"
    COMOROS = "km", "Comoros"
    CONGO = "cg", "Congo"
    CONGO_THE_DEMOCRATIC_REPUBLIC_OF_THE = "cd", "Congo, the Democratic Republic of the"
    COOK_ISLANDS = "ck", "Cook Islands"
    COSTA_RICA = "cr", "Costa Rica"
    COTE_DIVOIRE = "ci", "Cote D'ivoire"
    CROATIA = "hr", "Croatia"
    CUBA = "cu", "Cuba"
    CYPRUS = "cy", "Cyprus"
    CZECH_REPUBLIC = "cz", "Czech Republic"
    DENMARK = "dk", "Denmark"
    DJIBOUTI = "dj", "Djibouti"
    DOMINICA = "dm", "Dominica"
    DOMINICAN_REPUBLIC = "do", "Dominican Republic"
    ECUADOR = "ec", "Ecuador"
    EGYPT = "eg", "Egypt"
    EL_SALVADOR = "sv", "El Salvador"
    EQUATORIAL_GUINEA = "gq", "Equatorial Guinea"
    ERITREA = "er", "Eritrea"
    ESTONIA = "ee", "Estonia"
    ETHIOPIA = "et", "Ethiopia"
    FALKLAND_ISLANDS_MALVINAS = "fk", "Falkland Islands (Malvinas)"
    FAROE_ISLANDS = "fo", "Faroe Islands"
    FIJI = "fj", "Fiji"
    FINLAND = "fi", "Finland"
    FRANCE = "fr", "France"
    FRENCH_GUIANA = "gf", "French Guiana"
    FRENCH_POLYNESIA = "pf", "French Polynesia"
    FRENCH_SOUTHERN_TERRITORIES = "tf", "French Southern Territories"
    GABON = "ga", "Gabon"
    GAMBIA = "gm", "Gambia"
    GEORGIA = "ge", "Georgia"
    GERMANY = "de", "Germany"
    GHANA = "gh", "Ghana"
    GIBRALTAR = "gi", "Gibraltar"
    GREECE = "gr", "Greece"
    GREENLAND = "gl", "Greenland"
    GRENADA = "gd", "Grenada"
    GUADELOUPE = "gp", "Guadeloupe"
    GUAM = "gu", "Guam"
    GUATEMALA = "gt", "Guatemala"
    GUINEA = "gn", "Guinea"
    GUINEA_BISSAU = "gw", "Guinea-Bissau"
    GUYANA = "gy", "Guyana"
    HAITI = "ht", "Haiti"
    HEARD_ISLAND_AND_MCDONALD_ISLANDS = "hm", "Heard Island and Mcdonald Islands"
    HOLY_SEE_VATICAN_CITY_STATE = "va", "Holy See (Vatican City State)"
    HONDURAS = "hn", "Honduras"
    HONG_KONG = "hk", "Hong Kong"
    HUNGARY = "hu", "Hungary"
    ICELAND = "is", "Iceland"
    INDIA = "in", "India"
    INDONESIA = "id", "Indonesia"
    IRAN_ISLAMIC_REPUBLIC_OF = "ir", "Iran, Islamic Republic of"
    IRAQ = "iq", "Iraq"
    IRELAND = "ie", "Ireland"
    ISRAEL = "il", "Israel"
    ITALY = "it", "Italy"
    JAMAICA = "jm", "Jamaica"
    JAPAN = "jp", "Japan"
    JORDAN = "jo", "Jordan"
    KAZAKHSTAN = "kz", "Kazakhstan"
    KENYA = "ke", "Kenya"
    KIRIBATI = "ki", "Kiribati"
    KOREA_DEMOCRATIC_PEOPLES_REPUBLIC_OF = (
        "kp",
        "Korea, Democratic People's Republic of",
    )
    KOREA_REPUBLIC_OF = "kr", "Korea, Republic of"
    KUWAIT = "kw", "Kuwait"
    KYRGYZSTAN = "kg", "Kyrgyzstan"
    LAO_PEOPLES_DEMOCRATIC_REPUBLIC = "la", "Lao People's Democratic Republic"
    LATVIA = "lv", "Latvia"
    LEBANON = "lb", "Lebanon"
    LESOTHO = "ls", "Lesotho"
    LIBERIA = "lr", "Liberia"
    LIBYAN_ARAB_JAMAHIRIYA = "ly", "Libyan Arab Jamahiriya"
    LIECHTENSTEIN = "li", "Liechtenstein"
    LITHUANIA = "lt", "Lithuania"
    LUXEMBOURG = "lu", "Luxembourg"
    MACAO = "mo", "Macao"
    MACEDONIA_THE_FORMER_YUGOSLAV_REPUBLIC_OF = (
        "mk",
        "Macedonia, the Former Yugoslav Republic of",
    )
    MADAGASCAR = "mg", "Madagascar"
    MALAWI = "mw", "Malawi"
    MALAYSIA = "my", "Malaysia"
    MALDIVES = "mv", "Maldives"
    MALI = "ml", "Mali"
    MALTA = "mt", "Malta"
    MARSHALL_ISLANDS = "mh", "Marshall Islands"
    MARTINIQUE = "mq", "Martinique"
    MAURITANIA = "mr", "Mauritania"
    MAURITIUS = "mu", "Mauritius"
    MAYOTTE = "yt", "Mayotte"
    MEXICO = "mx", "Mexico"
    MICRONESIA_FEDERATED_STATES_OF = "fm", "Micronesia, Federated States of"
    MOLDOVA_REPUBLIC_OF = "md", "Moldova, Republic of"
    MONACO = "mc", "Monaco"
    MONGOLIA = "mn", "Mongolia"
    MONTSERRAT = "ms", "Montserrat"
    MOROCCO = "ma", "Morocco"
    MOZAMBIQUE = "mz", "Mozambique"
    MYANMAR = "mm", "Myanmar"
    NAMIBIA = "na", "Namibia"
    NAURU = "nr", "Nauru"
    NEPAL = "np", "Nepal"
    NETHERLANDS = "nl", "Netherlands"
    NETHERLANDS_ANTILLES = "an", "Netherlands Antilles"
    NEW_CALEDONIA = "nc", "New Caledonia"
    NEW_ZEALAND = "nz", "New Zealand"
    NICARAGUA = "ni", "Nicaragua"
    NIGER = "ne", "Niger"
    NIGERIA = "ng", "Nigeria"
    NIUE = "nu", "Niue"
    NORFOLK_ISLAND = "nf", "Norfolk Island"
    NORTHERN_MARIANA_ISLANDS = "mp", "Northern Mariana Islands"
    NORWAY = "no", "Norway"
    OMAN = "om", "Oman"
    PAKISTAN = "pk", "Pakistan"
    PALAU = "pw", "Palau"
    PALESTINIAN_TERRITORY_OCCUPIED = "ps", "Palestinian Territory, Occupied"
    PANAMA = "pa", "Panama"
    PAPUA_NEW_GUINEA = "pg", "Papua New Guinea"
    PARAGUAY = "py", "Paraguay"
    PERU = "pe", "Peru"
    PHILIPPINES = "ph", "Philippines"
    PITCAIRN = "pn", "Pitcairn"
    POLAND = "pl", "Poland"
    PORTUGAL = "pt", "Portugal"
    PUERTO_RICO = "pr", "Puerto Rico"
    QATAR = "qa", "Qatar"
    REUNION = "re", "Reunion"
    ROMANIA = "ro", "Romania"
    RUSSIAN_FEDERATION = "ru", "Russian Federation"
    RWANDA = "rw", "Rwanda"
    SAINT_HELENA = "sh", "Saint Helena"
    SAINT_KITTS_AND_NEVIS = "kn", "Saint Kitts and Nevis"
    SAINT_LUCIA = "lc", "Saint Lucia"
    SAINT_PIERRE_AND_MIQUELON = "pm", "Saint Pierre and Miquelon"
    SAINT_VINCENT_AND_THE_GRENADINES = "vc", "Saint Vincent and the Grenadines"
    SAMOA = "ws", "Samoa"
    SAN_MARINO = "sm", "San Marino"
    SAO_TOME_AND_PRINCIPE = "st", "Sao Tome and Principe"
    SAUDI_ARABIA = "sa", "Saudi Arabia"
    SENEGAL = "sn", "Senegal"
    SERBIA_AND_MONTENEGRO = "rs", "Serbia and Montenegro"
    SEYCHELLES = "sc", "Seychelles"
    SIERRA_LEONE = "sl", "Sierra Leone"
    SINGAPORE = "sg", "Singapore"
    SLOVAKIA = "sk", "Slovakia"
    SLOVENIA = "si", "Slovenia"
    SOLOMON_ISLANDS = "sb", "Solomon Islands"
    SOMALIA = "so", "Somalia"
    SOUTH_AFRICA = "za", "South Africa"
    SOUTH_GEORGIA_AND_THE_SOUTH_SANDWICH_ISLANDS = (
        "gs",
        "South Georgia and the South Sandwich Islands",
    )
    SPAIN = "es", "Spain"
    SRI_LANKA = "lk", "Sri Lanka"
    SUDAN = "sd", "Sudan"
    SURINAME = "sr", "Suriname"
    SVALBARD_AND_JAN_MAYEN = "sj", "Svalbard and Jan Mayen"
    SWAZILAND = "sz", "Swaziland"
    SWEDEN = "se", "Sweden"
    SWITZERLAND = "ch", "Switzerland"
    SYRIAN_ARAB_REPUBLIC = "sy", "Syrian Arab Republic"
    TAIWAN_PROVINCE_OF_CHINA = "tw", "Taiwan, Province of China"
    TAJIKISTAN = "tj", "Tajikistan"
    TANZANIA_UNITED_REPUBLIC_OF = "tz", "Tanzania, United Republic of"
    THAILAND = "th", "Thailand"
    TIMOR_LESTE = "tl", "Timor-Leste"
    TOGO = "tg", "Togo"
    TOKELAU = "tk", "Tokelau"
    TONGA = "to", "Tonga"
    TRINIDAD_AND_TOBAGO = "tt", "Trinidad and Tobago"
    TUNISIA = "tn", "Tunisia"
    TURKEY = "tr", "Turkey"
    TURKMENISTAN = "tm", "Turkmenistan"
    TURKS_AND_CAICOS_ISLANDS = "tc", "Turks and Caicos Islands"
    TUVALU = "tv", "Tuvalu"
    UGANDA = "ug", "Uganda"
    UKRAINE = "ua", "Ukraine"
    UNITED_ARAB_EMIRATES = "ae", "United Arab Emirates"
    UNITED_KINGDOM = "gb", "United Kingdom"
    UNITED_STATES = "us", "United States"
    UNITED_STATES_MINOR_OUTLYING_ISLANDS = "um", "United States Minor Outlying Islands"
    URUGUAY = "uy", "Uruguay"
    UZBEKISTAN = "uz", "Uzbekistan"
    VANUATU = "vu", "Vanuatu"
    VENEZUELA = "ve", "Venezuela"
    VIET_NAM = "vn", "Viet Nam"
    VIRGIN_ISLANDS_BRITISH = "vg", "Virgin Islands, British"
    VIRGIN_ISLANDS_US = "vi", "Virgin Islands, U.S."
    WALLIS_AND_FUTUNA = "wf", "Wallis and Futuna"
    WESTERN_SAHARA = "eh", "Western Sahara"
    YEMEN = "ye", "Yemen"
    ZAMBIA = "zm", "Zambia"
    ZIMBABWE = "zw", "Zimbabwe"


class GoogleSearchLocationMixin(BaseModel):
    serp_search_location: SerpSearchLocation | None = Field(
        title="Web Search Location",
    )
    scaleserp_locations: list[str] | None = Field(
        description="DEPRECATED: use `serp_search_location` instead"
    )


class GoogleSearchMixin(GoogleSearchLocationMixin, BaseModel):
    serp_search_type: SerpSearchType | None = Field(
        title="Web Search Type",
    )
    scaleserp_search_field: str | None = Field(
        description="DEPRECATED: use `serp_search_type` instead"
    )
