import gooey_gui as gui

from pydantic import BaseModel


class TrainingDataModel(BaseModel):
    prompt: str
    completion: str


def text_training_data(label1: str, label2: str, *, key: str):
    training_data = gui.session_state.get(key, [])

    data_area = gui.div()

    add = gui.button("Add an example", help=f"Add {key}")
    if add:
        training_data.append({"prompt": "", "completion": ""})

    with data_area:
        for idx, value in enumerate(training_data):
            col1, col2 = gui.columns([1, 10])

            with col1:
                btn_area = gui.div()
                # pressed_delete = btn_area.button(f"🗑", help=f"Delete {key} {idx + 1}")
                pressed_delete = False
                if pressed_delete:
                    training_data.pop(idx)
                    btn_area.empty()
                    continue

            with col2:
                value["prompt"] = gui.text_area(
                    label1,
                    help=f"{key} {label1} {idx + 1}",
                    value=value["prompt"],
                    height=100,
                )
                value["completion"] = gui.text_area(
                    label2,
                    help=f"{key} {label2} {idx + 1}",
                    value=value["completion"],
                    height=200,
                )

    gui.session_state[key] = training_data
    return training_data
