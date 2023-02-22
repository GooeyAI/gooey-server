import sentry_sdk
import streamlit as st
from firebase_admin import auth
from firebase_admin.auth import UserRecord
from furl import furl
from streamlit import runtime
from streamlit.runtime.scriptrunner import get_script_run_ctx
from streamlit.web.server.browser_websocket_handler import BrowserWebSocketHandler

from daras_ai_v2.copy_to_clipboard_button_widget import st_like_btn_css_html
from daras_ai_v2.hidden_html_widget import hidden_html_js, hidden_html_nojs
from daras_ai_v2.html_spinner_widget import html_spinner_css
from daras_ai_v2.query_params import gooey_get_query_params
from daras_ai_v2.query_params_util import extract_query_params
from daras_ai_v2.st_session_cookie import get_current_user, get_anonymous_user


def init_scripts():
    st.set_page_config(layout="wide")

    # remove fullscreen button and footer
    hidden_html_nojs(
        # language=html
        """
<style>
button[kind="primary"] {
    background-color: #b2ebf2;
    text-shadow: 0 0 0 black;
    color: transparent;  
}

.element-container {
    opacity:1 !important
}

.row-widget:has(button[kind="primary"]) {
    text-align: right;
}

button[title="View fullscreen"], footer {
    visibility: hidden;
}

textarea, input[type=text] {
    -webkit-text-fill-color: white !important;
    color: white !important;
}

.stMultiSelect [data-baseweb=select] span {
    max-width: 500px;
    color: black;
}

.stTabs [data-baseweb=tab] p {
    font-size: 1.2rem;
} 
.stTabs [data-baseweb=tab] {
    padding: 25px 0;
    padding-right: 10px;
} 
.stTabs [data-baseweb=tab-list] {
    overflow-y: hidden;
}
.stTabs [data-baseweb=tab-border] {
    margin-bottom: 10px;
}

.streamlit-expanderHeader p {
    font-size: 1.1rem;
}

video, img {
    max-width: 350px;
    max-height: 350px;
    border-radius: 5px;
}

.stSpinner * {
    font-size: 1.1rem;
}

.stCodeBlock * code {
    white-space: pre-wrap !important;
}
.stCodeBlock pre {
    padding: 0.75rem !important;
}
.stCodeBlock pre div {
    max-height: 500px;
    overflow-x: clip;
    overflow-y: scroll;
}

.stTooltipIcon * svg {
    display: none !important;
}
        
.gooey-output-text {
    background-color: rgb(32, 32, 32);
    overflow-y: scroll;
    border-radius: 5px;
    margin-bottom: 1rem;
}
.gooey-output-text p {
    padding: 0.75rem;
    margin: 0;
}

sup {
    font-size: 80%%;
    line-height: 0;
    position: relative;
    vertical-align: initial;
    top: -0.5em;
    padding: 0 2px;
}
sup a {
    text-decoration: none;
    font-weight: bold;
    color: #03dac5;
    padding: 0 1px;
}
sup a:hover {
    color: #acd9d6;
}
</style>
        """
        + st_like_btn_css_html
        + html_spinner_css
    )

    # for automatically resizing the iframe
    hidden_html_js(
        # language=html
        """
<script>
const stBlock = parent.document.querySelector('[data-testid="stVerticalBlock"]');

const observer = new ResizeObserver(entries => {
    notifyHeight(entries[0].contentRect.height);
});
observer.observe(stBlock);

setInterval(function() {
    notifyHeight(stBlock.clientHeight)
}, 500);

let lastHeight = 0;

function notifyHeight(height) {
    if (lastHeight == height) return;
    lastHeight = height;
    top.postMessage({ type: "GOOEY_IFRAME_RESIZE", height: height }, "*");
}
</script>

<script>
parent.document.addEventListener("click", (e) => {
    if (e.target.tagName == "IMG") {
        window.open(e.target.src);                    
    }
});
</script>
        """,
        is_static=True,
    )

    if "_current_user" not in st.session_state:
        st.session_state["_current_user"] = get_current_user() or get_anonymous_user()

    current_user = st.session_state.get("_current_user")
    if not current_user:
        st.error("Sorry, we can't let you do that! Please login to continue.")
        st.stop()

    query_params = gooey_get_query_params()
    _, _, uid = extract_query_params(query_params)
    run_user: UserRecord = st.session_state.get("_run_user")
    if uid and (not run_user or run_user.uid != uid):
        if current_user.uid == uid:
            user = current_user
        else:
            user: UserRecord = auth.get_user(uid)
        st.session_state["_run_user"] = user

    with sentry_sdk.configure_scope() as scope:
        scope.set_user(
            {
                "id": current_user.uid,
                "username": current_user.display_name,
                "email": current_user.email,
                "phone_number": current_user.phone_number,
                "photo_url": current_user.photo_url,
            }
        )
        request = _st_session_client().request
        scope.set_extra("ws_request", request)
        scope.set_extra("query_params", gooey_get_query_params())
        scope.add_event_processor(_event_processor)


def _event_processor(event, hint):
    extra = event.get("extra")
    if extra:
        request_data = {"data": st.session_state.to_dict()}
        base_url = extra.get("base_url")
        if base_url:
            query_params = extra.get("query_params", {})
            request_data["url"] = str(furl(base_url, query_params=query_params))
        ws_request = extra.get("ws_request")
        if ws_request:
            request_data["method"] = ws_request.method
            request_data["headers"] = ws_request.headers
            request_data["env"] = {"REMOTE_ADDR": ws_request.remote_ip}
        event["request"] = request_data
    return event


def _st_session_client():
    ctx = get_script_run_ctx()
    if ctx is None:
        return None

    session_client = runtime.get_instance().get_client(ctx.session_id)
    if session_client is None:
        return None

    if not isinstance(session_client, BrowserWebSocketHandler):
        raise RuntimeError(
            f"SessionClient is not a BrowserWebSocketHandler! ({session_client})"
        )

    return session_client
