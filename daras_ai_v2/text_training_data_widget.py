import streamlit as st

from pydantic import BaseModel


class TrainingDataModel(BaseModel):
    prompt: str
    completion: str

    class Config:
        schema_extra = {
            "example": {
                "prompt": "Extreme weather events, both extreme cold and extreme heat will probably increase in frequency due to climate change.",
                "completion": "Dear Senate Rules Committee Members, Please pull HB 1620 out of the Rules Committee and send it for a floor vote",
            }
        }


def text_training_data(label1: str, label2: str, *, key: str):
    training_data = st.session_state.get(key, [])

    data_area = st.empty()

    add = st.button("Add an example", help=f"Add {key}")
    if add:
        training_data.append({"prompt": "", "completion": ""})

    with data_area.container():
        for idx, value in enumerate(training_data):
            col1, col2 = st.columns([1, 10])

            with col1:
                btn_area = st.empty()
                pressed_delete = btn_area.button(f"🗑", help=f"Delete {key} {idx + 1}")
                if pressed_delete:
                    training_data.pop(idx)
                    btn_area.empty()
                    continue

            with col2:
                value["prompt"] = st.text_area(
                    label1,
                    help=f"{key} {label1} {idx + 1}",
                    value=value["prompt"],
                    height=100,
                )
                value["completion"] = st.text_area(
                    label2,
                    help=f"{key} {label2} {idx + 1}",
                    value=value["completion"],
                    height=200,
                )

    st.session_state[key] = training_data
    return training_data
