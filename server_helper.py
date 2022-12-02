from server import ANONYMOUS_USER_COOKIE


def get_uid(request):
    if request.user:
        return request.user.uid
    else:
        return request.session.get(ANONYMOUS_USER_COOKIE)["uid"]
