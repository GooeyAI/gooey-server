import urllib.parse


class RedirectException(Exception):
    def __init__(self, url, status_code=302):
        self.url = url
        self.status_code = status_code


class QueryParamsRedirectException(RedirectException):
    def __init__(self, query_params: dict, status_code=303):
        query_params = {k: v for k, v in query_params.items() if v is not None}
        url = "?" + urllib.parse.urlencode(query_params)
        super().__init__(url, status_code)


class StopException(Exception):
    pass


class RerunException(Exception):
    pass


def rerun():
    raise RerunException()


def stop():
    raise StopException()
