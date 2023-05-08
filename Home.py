def main():
    from daras_ai.init import init_scripts

    init_scripts()

    import gooey_ui as st
    from server import normalize_slug, page_map
    import explore

    # try to load page from query params
    #
    query_params = st.get_query_params()
    try:
        page_slug = normalize_slug(query_params["page_slug"])
    except KeyError:
        # otherwise, render the explore page
        #
        explore.render()
    else:
        try:
            page = page_map[page_slug]
        except KeyError:
            st.error(f"## 404 - Page {page_slug!r} Not found")
        else:
            page().render()
