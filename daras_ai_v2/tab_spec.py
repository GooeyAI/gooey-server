import typing

import pydantic

# NOTE: this module is imported by both daras_ai_v2.base_v2 and routers.recipe_v2, so it
# must not import either of them at module level.


class TabSpec(pydantic.BaseModel):
    """One tab of a layout-v2 recipe page, as declared by `BasePage.get_tab_spec()`.

    Only `slug`, `label` and `icon` are serialized - they are all the top bar needs to draw
    links. `render` stays on the server.
    """

    slug: str
    """Url segment AND identity. "" is the entry url `/{page_slug}/`, which v1 owns."""

    label: str
    icon: str = ""
    """Raw FontAwesome html, like `NavItemData.icon`."""

    # server-only: the top bar renders links and labels, never behaviour
    render: typing.Callable[[], None] = pydantic.Field(exclude=True)


class TabRoute(typing.NamedTuple):
    """Gives a v2 tab slug the same `.url_path()` interface `RecipeTabs` has, so that
    `BasePage.app_url()` & friends can build v2 tab urls without duplicating their
    example_id / run_id / query param handling.
    """

    slug: str

    def url_path(
        self,
        page_slug: str,
        run_slug: str | None = None,
        example_id: str | None = None,
        **path_params,
    ) -> str:
        # lazy: routers.recipe_v2 imports the v2 page classes, which import this module
        from routers.recipe_v2 import tab_url_path

        return tab_url_path(
            self.slug,
            page_slug=page_slug,
            run_slug=run_slug,
            example_id=example_id,
            **path_params,
        )
