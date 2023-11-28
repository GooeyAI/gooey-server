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

    def is_open(self):
        return st.session_state.get(f"{self.key}-opened", False)

    def open(self):
        st.session_state[f"{self.key}-opened"] = True
        rerun()

    def close(self, rerun_condition=True):
        st.session_state[f"{self.key}-opened"] = False
        if rerun_condition:
            rerun()

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
            z-index: 1000;
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
            padding: 3rem;
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
                container = st.div(className=container_class, **props)

        with container:
            with st.div(className="d-flex justify-content-between align-items-center"):
                st.markdown(f"## {self.title or ''}")

                close_ = st.button(
                    "&#10006;",
                    key=f"{self.key}-close",
                    style={"padding": "0.375rem 0.75rem"},
                )
                if close_:
                    self.close()
            yield

        return

        st.markdown(
            f"""
            <style>
            div[data-modal-container='true'][key='{self.key}'] {{
                position: fixed;
                width: 100vw !important;
                left: 0;
                z-index: 999992;
            }}

            div[data-modal-container='true'][key='{self.key}'] > div:first-child {{
                margin: auto;
            }}

            div[data-modal-container='true'][key='{self.key}'] h1 a {{
                display: none
            }}

            div[data-modal-container='true'][key='{self.key}']::before {{
                    position: fixed;
                    content: ' ';
                    left: 0;
                    right: 0;
                    top: 0;
                    bottom: 0;
                    z-index: 1000;
                    background-color: rgba(0, 0, 0, 0.5);
            }}
            div[data-modal-container='true'][key='{self.key}'] > div:first-child {{
                max-width: {self.max_width};
            }}

            div[data-modal-container='true'][key='{self.key}'] > div:first-child > div:first-child {{
                width: unset !important;
                background-color: #fff;
                padding: {self.padding}px;
                margin-top: {2*self.padding}px;
                margin-left: -{self.padding}px;
                margin-right: -{self.padding}px;
                margin-bottom: -{2*self.padding}px;
                z-index: 1001;
                border-radius: 5px;
            }}
            div[data-modal-container='true'][key='{self.key}'] > div:first-child > div:first-child > div:first-child  {{
                overflow-y: scroll;
                max-height: 80vh;
                overflow-x: hidden;
                max-width: {self.max_width};
            }}

            div[data-modal-container='true'][key='{self.key}'] > div > div:nth-child(2)  {{
                z-index: 1003;
                position: absolute;
            }}
            div[data-modal-container='true'][key='{self.key}'] > div > div:nth-child(2) > div {{
                text-align: right;
                padding-right: {self.padding}px;
                max-width: {self.max_width};
            }}

            div[data-modal-container='true'][key='{self.key}'] > div > div:nth-child(2) > div > button {{
                right: 0;
                margin-top: {2*self.padding + 14}px;
            }}
            </style>
            """,
            unsafe_allow_html=True,
        )
        with st.div(className="container"):
            _container = st.div(className="container")
            if self.title:
                with _container:
                    st.markdown(f"<h2>{self.title}</h2>", unsafe_allow_html=True)

            close_ = st.button("&#10006;", key=f"{self.key}-close")
            if close_:
                self.close()

        with _container:
            yield _container
