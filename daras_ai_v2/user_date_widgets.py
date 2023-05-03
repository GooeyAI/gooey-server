import datetime

from streamlit2 import markdown

from daras_ai_v2.hidden_html_widget import hidden_html_js


def js_dynamic_date(dt: datetime.datetime):
    timestamp_ms = dt.timestamp() * 1000
    markdown(
        # language=HTML
        f'<span style="padding-left: 4px" data-id-dynamic-date="{timestamp_ms}"></span>',
        unsafe_allow_html=True,
    )


def render_js_dynamic_dates():
    hidden_html_js(
        # language=HTML
        """
<script>
const dateOptions = {
    weekday: "short",
    day: "numeric",
    month:  "short",
};
const timeOptions = {
    hour: "numeric",
    hour12: true,
    minute: "numeric",
};

parent.document.querySelectorAll("[data-id-dynamic-date]").forEach(elem => {
    let date = new Date(parseFloat(elem.getAttribute("data-id-dynamic-date")));
    let yearToShow = "";
    if (date.getFullYear() != new Date().getFullYear()) {
        yearToShow = " " + date.getFullYear().toString();
    } 
    elem.innerHTML = `
        <i>
            ${date.toLocaleDateString("en-IN", dateOptions)}${yearToShow},
            ${date.toLocaleTimeString("en-IN", timeOptions).toUpperCase()}
        </i> 
    `;
});
</script>
        """,
        is_static=True,
    )
