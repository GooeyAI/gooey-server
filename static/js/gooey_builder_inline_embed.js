async function onload() {
  await window.waitUntilHydrated;

  // library not loaded yet, skip
  if (typeof GooeyEmbed === "undefined") return;

  // widget already mounted, return
  if (document.getElementById("gooey-builder-embed")?.children.length) {
    loadData();
    return;
  }

  if (conversation_data) {
    config.conversationData = conversation_data;
  }
  config.onClose = function () {
    window.dispatchEvent(new CustomEvent(`${sidebar_key}:close`));
  };

  GooeyEmbed.gooeyBuilderControl = {
    // this is a trick to update the variables after the widget is already mounted
    setPayloadVariables: (value) => {
      config.payload.variables = value;
    },
  };
  GooeyEmbed.mount(config, GooeyEmbed.gooeyBuilderControl);
  loadData();
}

function loadData() {
  let controller = GooeyEmbed.gooeyBuilderControl;
  if (!controller) return;
  controller.setPayloadVariables(variables);
  if (conversation_data) {
    controller.setConversationData?.(conversation_data);
  }
  controller.onConversationChange = function (conversationId) {
    // avoid redundant redirect back to the same run.
    if (conversationId === conversation_data?.id) return;
    window.gui.update_session_state({
      builder_selected_conversation: conversationId,
    });
  };
}

const script = document.getElementById("gooey-embed-script");
if (script) script.onload = onload;
onload();
window.addEventListener("hydrated", onload);
