from gooey_gui.components import common as gui


def url_button(url):
    gui.html(
        f"""
<a href='{url}' target='_blank'>
    <button type="button" class="btn btn-theme btn-tertiary">
        <i class="fa-regular fa-external-link-square"></i>
    </button>
</a>
        """
    )
