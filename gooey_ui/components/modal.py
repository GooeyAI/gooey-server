from contextlib import contextmanager

import gooey_ui as st
from gooey_ui import experimental_rerun as rerun


class Modal:
    def __init__(self, title, key, padding=20, max_width=744):
        """
        :param title: title of the Modal shown in the h1
        :param key: unique key identifying this modal instance
        :param padding: padding of the content within the modal
        :param max_width: maximum width this modal should use
        """
        self.title = title
        self.padding = padding
        self.max_width = str(max_width) + "px"
        self.key = key

        self._container = None

    def is_open(self):
        return st.session_state.get(f"{self.key}-opened", False)

    def open(self):
        st.session_state[f"{self.key}-opened"] = True
        rerun()

    def close(self, rerun_condition=True):
        st.session_state[f"{self.key}-opened"] = False
        if rerun_condition:
            rerun()

    def empty(self):
        if self._container:
            self._container.empty()

    @contextmanager
    def container(self, **props):
        st.html(
            f"""
        <style>
        .blur-background {{
            position: fixed;
            content: ' ';
            left: 0;
            right: 0;
            top: 0;
            bottom: 0;
            z-index: 9999;
            background-color: rgba(0, 0, 0, 0.5);
        }}
        .modal-parent {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            z-index: 2000;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .modal-container {{
            overflow-y: scroll;
            padding: 1.5rem;
            margin: auto;
            background: white;
            z-index: 3000;
            max-height: 80vh;
        }}
        </style>
        """
        )

        with st.div(className="blur-background"):
            with st.div(className="modal-parent"):
                container_class = "modal-container " + props.pop("className", "")
                self._container = st.div(className=container_class, **props)

        with self._container:
            with st.div(className="d-flex justify-content-between align-items-center"):
                st.markdown(f"### {self.title or ''}")

                close_ = st.button(
                    "&#10006;",
                    type="tertiary",
                    key=f"{self.key}-close",
                    style={"padding": "0.375rem 0.75rem"},
                )
                if close_:
                    self.close()
            yield self._container


class ConfirmationModal(Modal):
    def __init__(
        self,
        *,
        title: str,
        key: str,
        confirm_text: str = "Confirm",
        cancel_text: str = "Cancel",
        confirm_button_props: dict | None = None,
        cancel_button_props: dict | None = None,
        **props,
    ):
        super().__init__(title, key, **props)

        self.confirm_text = confirm_text
        self.cancel_text = cancel_text
        self.confirm_button_props = {"type": "secondary", "className": "w-100"} | (
            confirm_button_props or {}
        )
        self.cancel_button_props = {"type": "secondary", "className": "w-100"} | (
            cancel_button_props or {}
        )

        self.is_confirm_pressed = False

    @contextmanager
    def container(self):
        with super().container():
            div = st.div()

            with st.div(className="d-flex"):
                confirm_button = st.button(
                    self.confirm_text,
                    key=f"{self.key}-confirm",
                    **self.confirm_button_props,
                )
                cancel_button = st.button(
                    self.cancel_text,
                    key=f"{self.key}-cancel",
                    **self.cancel_button_props,
                )

            if cancel_button:
                self.close()

            self.is_confirm_pressed = confirm_button

            with div:
                yield
