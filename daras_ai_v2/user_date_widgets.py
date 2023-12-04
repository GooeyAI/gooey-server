import datetime
import json
from typing import Any

import gooey_ui as gui


def js_dynamic_date(
    dt: datetime.datetime,
    *,
    date_options: dict[str, Any] | None = None,
    time_options: dict[str, Any] | None = None,
):
    timestamp_ms = dt.timestamp() * 1000
    attrs = {"data-id-dynamic-date": str(timestamp_ms)}
    if date_options:
        attrs["data-id-date-options"] = json.dumps(date_options)
    if time_options:
        attrs["data-id-time-options"] = json.dumps(time_options)
    gui.caption("Loading...", **attrs)


def render_js_dynamic_dates():
    default_date_options = {
        "weekday": "short",
        "day": "numeric",
        "month": "short",
    }
    default_time_options = {
        "hour": "numeric",
        "hour12": True,
        "minute": "numeric",
    }
    gui.html(
        # language=HTML
        """
<script>
async function render_js_dynamic_dates() {
    const defaultDateOptions = JSON.parse(`%(date_options_json)s`);
    const defaultTimeOptions = JSON.parse(`%(time_options_json)s`);

    function getOptions(elem, attr, defaultValue) {
        options = elem.getAttribute(attr);
        return options ? JSON.parse(options) : defaultValue;
    }

    document.querySelectorAll("[data-id-dynamic-date]").forEach(elem => {
        let dateOptions = getOptions(elem, "data-id-date-options", defaultDateOptions);
        let timeOptions = getOptions(elem, "data-id-time-options", defaultTimeOptions);
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
}
window.waitUntilHydrated.then(render_js_dynamic_dates);
window.addEventListener("hydrated", render_js_dynamic_dates);
</script>
        """
        % {
            "date_options_json": json.dumps(default_date_options),
            "time_options_json": json.dumps(default_time_options),
        },
    )


def re_render_js_dynamic_dates():
    gui.html(
        # language=HTML
        """
        <script>
        render_js_dynamic_dates();
        </script>
        """,
    )
