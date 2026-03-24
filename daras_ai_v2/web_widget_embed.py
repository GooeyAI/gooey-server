import gooey_gui as gui

from daras_ai_v2 import settings


def load_web_widget_lib():
    gui.html(
        f'<script id="gooey-embed-script" src="{settings.WEB_WIDGET_LIB}"></script>'
    )
