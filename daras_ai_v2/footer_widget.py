import gooey_ui as st

DISCORD_LOGO = """
<svg stroke="currentColor" fill="currentColor" stroke-width="2" viewBox="0 0 640 512"
        style="width: 18px; height: 16px; margin-bottom: 1px; padding-bottom: 1px;"
        xmlns="http://www.w3.org/2000/svg">
    <path d="M524.531,69.836a1.5,1.5,0,0,0-.764-.7A485.065,485.065,0,0,0,404.081,32.03a1.816,1.816,0,0,0-1.923.91,337.461,337.461,0,0,0-14.9,30.6,447.848,447.848,0,0,0-134.426,0,309.541,309.541,0,0,0-15.135-30.6,1.89,1.89,0,0,0-1.924-.91A483.689,483.689,0,0,0,116.085,69.137a1.712,1.712,0,0,0-.788.676C39.068,183.651,18.186,294.69,28.43,404.354a2.016,2.016,0,0,0,.765,1.375A487.666,487.666,0,0,0,176.02,479.918a1.9,1.9,0,0,0,2.063-.676A348.2,348.2,0,0,0,208.12,430.4a1.86,1.86,0,0,0-1.019-2.588,321.173,321.173,0,0,1-45.868-21.853,1.885,1.885,0,0,1-.185-3.126c3.082-2.309,6.166-4.711,9.109-7.137a1.819,1.819,0,0,1,1.9-.256c96.229,43.917,200.41,43.917,295.5,0a1.812,1.812,0,0,1,1.924.233c2.944,2.426,6.027,4.851,9.132,7.16a1.884,1.884,0,0,1-.162,3.126,301.407,301.407,0,0,1-45.89,21.83,1.875,1.875,0,0,0-1,2.611,391.055,391.055,0,0,0,30.014,48.815,1.864,1.864,0,0,0,2.063.7A486.048,486.048,0,0,0,610.7,405.729a1.882,1.882,0,0,0,.765-1.352C623.729,277.594,590.933,167.465,524.531,69.836ZM222.491,337.58c-28.972,0-52.844-26.587-52.844-59.239S193.056,219.1,222.491,219.1c29.665,0,53.306,26.82,52.843,59.239C275.334,310.993,251.924,337.58,222.491,337.58Zm195.38,0c-28.971,0-52.843-26.587-52.843-59.239S388.437,219.1,417.871,219.1c29.667,0,53.307,26.82,52.844,59.239C470.715,310.993,447.538,337.58,417.871,337.58Z"></path>
</svg>
"""

FOOTER_CONTENT = {
    "GET STARTED": [
        ("Home", "/"),
        ("Explore Workflows", "/explore/"),
        ("Sign In / Your Account", "/account/"),
        ("Pricing", "/pricing"),
    ],
    "LEARN": [
        ("Docs", "/docs"),
        ("Blog", "/blog/"),
        ("FAQ", "/faq/"),
        ("Videos", "https://www.youtube.com/@gooeyAI"),
    ],
    "DEVELOPERS": [
        ("How to Guides", "/docs/"),
        ("Get a Gooey.AI Key", "/docs/developer-resources/api-reference"),
        ("GitHub", "https://github.com/GooeyAI"),
        ("API Endpoints", "https://api.gooey.ai/docs#operation"),
    ],
    "SOCIAL": [
        ("LinkedIn", "https://in.linkedin.com/company/gooeyai"),
        ("Twitter/X", "https://twitter.com/GooeyAI"),
        ("Insta", "https://www.instagram.com/gooeyai/"),
    ],
    "CONNECT": [
        ("support@gooey.ai", "mailto:support@gooey.ai"),
        (f"{DISCORD_LOGO} Discord", "https://discord.com/invite/7C84UyzVDg"),
        ("Book a Demo", "https://www.help.gooey.ai/contact#book-demo"),
    ],
    "EXTRAS": [
        ("Team", "/team"),
        ("Jobs", "/jobs"),
        ("Privacy", "/privacy"),
        ("Terms", "/terms"),
    ],
}


def footer():
    with st.div(className="w-100 mt-5 pt-5 bg-light gui-footer"):
        with st.div(className="container"):
            columns = st.columns(len(FOOTER_CONTENT))
            for (title, links), st_col in zip(FOOTER_CONTENT.items(), columns):
                with st_col:
                    render_column(title, links)

            with center(className="mt-5"):
                st.caption("©2023 by Gooey.AI / Dara.network Inc")


def render_column(title, links):
    st.write(f"###### {title}")
    for content, to in links:
        target = "_blank" if to.startswith("http") else False
        with st.link(to=to, target=target):
            custom_caption(content)


def custom_caption(content):
    with st.tag("p", className="text-muted mb-0"):
        st.html(content)


def center(**props):
    className = props.pop("className", "") + " text-center"
    return st.div(className=className, **props)
