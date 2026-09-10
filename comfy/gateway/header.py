"""
The Gooey header bar injected on top of the ComfyUI web app.

Injected as a <style> + <script> block into ComfyUI's index.html by the proxy
(script-based DOM insertion survives any changes to ComfyUI's markup). The bar
shows the Gooey logo, a workspace switcher, live credit balance, and the
logged-in user, and pushes the ComfyUI app down below itself.
"""

import json

from gateway import settings

HEADER_HEIGHT = 44


def render_snippet(session: dict) -> str:
    boot = json.dumps(
        {
            "displayName": session["display_name"],
            "photoUrl": session["photo_url"],
            "workspaces": session["workspaces"],
            "selectedWorkspaceId": session["selected_workspace_id"],
            "appBaseUrl": settings.GOOEY_APP_BASE_URL,
            "logoUrl": settings.GOOEY_LOGO_IMG_WHITE,
            "headerHeight": HEADER_HEIGHT,
        }
    )
    return STYLE + f"<script>window.__GOOEY__ = {boot};</script>" + SCRIPT


STYLE = f"""
<style id="gooey-header-style">
  html {{ --gooey-header-h: {HEADER_HEIGHT}px; }}
  body {{
    margin-top: {HEADER_HEIGHT}px !important;
    height: calc(100% - {HEADER_HEIGHT}px) !important;
  }}
  #vue-app, #app {{ height: calc(100vh - {HEADER_HEIGHT}px) !important; }}
  #gooey-header {{
    position: fixed; top: 0; left: 0; right: 0; height: {HEADER_HEIGHT}px;
    z-index: 99999; display: flex; align-items: center; gap: 12px;
    padding: 0 12px; box-sizing: border-box;
    background: #02023e; color: #fff;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    font-size: 13px; border-bottom: 1px solid rgba(255,255,255,.15);
  }}
  #gooey-header a {{ color: #fff; text-decoration: none; opacity: .9; }}
  #gooey-header a:hover {{ opacity: 1; text-decoration: underline; }}
  #gooey-header img.gooey-logo {{ height: 22px; }}
  #gooey-header .gooey-tag {{
    background: rgba(255,255,255,.15); border-radius: 4px; padding: 2px 6px;
    font-weight: 600; letter-spacing: .3px;
  }}
  #gooey-header .gooey-spacer {{ flex: 1; }}
  #gooey-header select {{
    background: rgba(255,255,255,.1); color: #fff; border: 1px solid
    rgba(255,255,255,.25); border-radius: 6px; padding: 3px 6px; font-size: 13px;
    max-width: 220px;
  }}
  #gooey-header select option {{ color: #000; }}
  #gooey-header .gooey-credits {{ white-space: nowrap; }}
  #gooey-header img.gooey-avatar {{
    height: 26px; width: 26px; border-radius: 50%; object-fit: cover;
  }}
</style>
"""

SCRIPT = """
<script id="gooey-header-script">
(function () {
  var G = window.__GOOEY__;
  function fmt(n) { return n.toLocaleString(); }

  function build() {
    if (document.getElementById("gooey-header")) return;
    var bar = document.createElement("div");
    bar.id = "gooey-header";

    var options = G.workspaces.map(function (w) {
      var sel = w.id === G.selectedWorkspaceId ? " selected" : "";
      return "<option value='" + w.id + "'" + sel + "></option>";
    }).join("");

    bar.innerHTML =
      "<a href='" + G.appBaseUrl + "' title='Back to Gooey.AI'>" +
        "<img class='gooey-logo' alt='Gooey.AI' src='" + G.logoUrl + "'/></a>" +
      "<span class='gooey-tag'>ComfyUI</span>" +
      "<span class='gooey-spacer'></span>" +
      "<label>Workspace <select id='gooey-workspace-select'>" + options +
        "</select></label>" +
      "<span class='gooey-credits' id='gooey-credits'></span>" +
      "<a href='" + G.appBaseUrl + "/account/' target='_blank'>Add credits</a>" +
      "<img class='gooey-avatar' id='gooey-avatar' alt=''/>" +
      "<span id='gooey-username'></span>" +
      "<a href='/gooey/logout'>Logout</a>";
    document.body.appendChild(bar);

    // set user-controlled strings via textContent/attributes, never innerHTML
    var select = document.getElementById("gooey-workspace-select");
    G.workspaces.forEach(function (w, i) {
      select.options[i].textContent = w.name;
    });
    document.getElementById("gooey-username").textContent = G.displayName;
    document.getElementById("gooey-avatar").src = G.photoUrl;
    renderCredits();

    select.addEventListener("change", function () {
      fetch("/gooey/switch-workspace", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workspace_id: parseInt(select.value, 10) }),
      }).then(function () { window.location.reload(); });
    });

    setInterval(refresh, 30000);
  }

  function renderCredits() {
    var w = G.workspaces.find(function (w) {
      return w.id === G.selectedWorkspaceId;
    });
    if (w) {
      document.getElementById("gooey-credits").textContent =
        fmt(w.balance) + " credits";
    }
  }

  function refresh() {
    fetch("/gooey/api/me").then(function (r) {
      if (r.status === 401) { window.location.href = "/login"; return; }
      return r.json();
    }).then(function (me) {
      if (!me) return;
      G.workspaces = me.workspaces;
      G.selectedWorkspaceId = me.selected_workspace_id;
      renderCredits();
    }).catch(function () {});
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", build);
  } else {
    build();
  }
})();
</script>
"""
