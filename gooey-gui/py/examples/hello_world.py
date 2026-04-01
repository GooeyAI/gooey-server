from fastapi import FastAPI

import gooey_gui as gui

app = FastAPI()


@gui.route(app, "/")
def root():
    gui.write(
        """
        # My first app
        Hello *world!*
        """
    )


@gui.route(app, "/temp/")
def root():
    temperature = gui.slider("Temperature", 0, 100, 50)
    gui.write(f"The temperature is {temperature}")
