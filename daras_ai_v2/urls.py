from furl import furl


def remove_hostname(url: str) -> str:
    full_url = furl(url)
    short_url = furl(full_url.path)
    short_url.query = str(full_url.query)
    short_url.fragment = str(full_url.fragment)
    return str(short_url)


def remove_scheme(url: str) -> str:
    return url.removeprefix("http://").removeprefix("https://")
