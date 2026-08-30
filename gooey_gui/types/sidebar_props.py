from typing import ClassVar, Literal

from gooey_gui.types import StrictComponentModel


class SidebarProps(StrictComponentModel):
    _component: ClassVar[Literal["Sidebar"]] = "Sidebar"

    name: str
    default_open: bool
    disabled: bool
    enable_resize: bool = True
    client_only: bool = False
    storage_key: str | None = None
