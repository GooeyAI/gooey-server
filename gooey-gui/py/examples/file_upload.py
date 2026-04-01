import os

from fastapi import Depends
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import FormData
from starlette.requests import Request

import gooey_gui as gui

if not os.path.exists("static"):
    os.mkdir("static")

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")


async def request_form_files(request: Request) -> FormData:
    return await request.form()


@app.post("/__/file-upload/")
def file_upload(form_data: FormData = Depends(request_form_files)):
    file = form_data["file"]
    data = file.file.read()
    filename = file.filename
    with open("static/" + filename, "wb") as f:
        f.write(data)
    return {"url": "http://localhost:3000/static/" + filename}


@gui.route(app, "/")
def upload():
    uploaded_file = gui.file_uploader("Upload an image", accept=["image/*"])
    if uploaded_file is not None:
        gui.image(uploaded_file)
