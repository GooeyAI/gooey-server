import datetime

import gooey_ui as gui

from daras_ai_v2.hidden_html_widget import hidden_html_js


def js_dynamic_date(dt: datetime.datetime):
    timestamp_ms = dt.timestamp() * 1000
    gui.caption("Loading...", **{"data-id-dynamic-date": str(timestamp_ms)})


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
window.addEventListener("hydrated", () => {
    document.querySelectorAll("[data-id-dynamic-date]").forEach(elem => {
        let date = new Date(parseFloat(elem.getAttribute("data-id-dynamic-date")));
        let yearToShow = "";
        if (date.getFullYear() != new Date().getFullYear()) {
            yearToShow = " " + date.getFullYear().toString();
        } 
        elem.children[0].innerHTML = `
                ${date.toLocaleDateString("en-IN", dateOptions)}${yearToShow},
                ${date.toLocaleTimeString("en-IN", timeOptions).toUpperCase()}
        `;
    });
});
</script>
        """,
        is_static=True,
    )
