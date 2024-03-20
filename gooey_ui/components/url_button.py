import gooey_ui as st


def url_button(url):
    st.html(
        f"""
<a href='{url}' target='_blank'>
    <button type="button" class="btn btn-theme btn-tertiary">
        <i class="fa-regular fa-external-link-square"></i>
    </button>
</a>
        """
    )
