from streamlit.components.v1 import html


def scrollable_html(text: str, *, height=500):
    html(
        """
        <head>
        <style>
        body {
            margin: 0;
        }
        .content {
            background-color: white;
            font-family: 'Arial', sans-serif;
            font-size: 15px;
            height: 500px;
            overflow: scroll;
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
        </div>
        """
        % text,
        height=height,
    )
