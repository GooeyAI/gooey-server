from threading import Thread
from time import sleep

from fastapi import FastAPI

import gooey_gui as gui

app = FastAPI()


@gui.route(app, "/")
def poems():
    count, set_count = gui.use_state(0)

    start_counter = gui.button("Start Counter")
    if start_counter:
        Thread(target=counter, args=[set_count]).start()

    gui.write(f"### Count: {count}")

    text = gui.text_input("Type Something here...")
    gui.write("**You typed:** " + text)


def counter(set_count):
    for i in range(10):
        set_count(i)
        sleep(1)
