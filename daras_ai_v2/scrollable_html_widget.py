from streamlit2 import html


def scrollable_html(
    text: str,
    *,
    height=500,
    css="""background-color: white;
color: black;
font-family: 'Arial', sans-serif;"""
):
    html(
        """<head>
<style>
body {
margin: 0;
}
.content {
%s
font-size: 15px;
max-height: %ipx;
overflow-y: scroll;
padding: 0 10px;
border-radius: 5px;
}
::-webkit-scrollbar {
background: transparent;
color: white;
width: 6px;
}
::-webkit-scrollbar-thumb {
background: gray;
border-radius: 100px;
}
</style>
<base target="_blank">
</head>

<div class="content">
%s
</div>"""
        % (css, height, text),
        height=height,
    )
