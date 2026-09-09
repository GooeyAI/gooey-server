from typing import ClassVar, Literal

import pydantic


class ErrorSnackbarProps(pydantic.BaseModel):
    _component: ClassVar[Literal["ErrorSnackbar"]] = "ErrorSnackbar"

    message: str
    snackbar_id: str
