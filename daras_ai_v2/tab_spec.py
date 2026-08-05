import pydantic


class TabSpec(pydantic.BaseModel):
    """One client-side view in the layout-v2 workspace selector."""

    slug: str
    """View identity; it is deliberately not a URL segment."""

    label: str
    icon: str = ""
    """Raw FontAwesome html, like `NavItemData.icon`."""

    desktop_only: bool = False
    """Hidden from the strip below `lg`. For tabs whose layout needs the width - Split is
    two columns side by side, which a phone cannot show."""

    immersive_on_mobile: bool = False
    """Below `lg`, this view fills the workspace below the app header."""
