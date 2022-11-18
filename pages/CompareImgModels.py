import typing

from daras_ai_v2.base import BasePage


class CompareImageModelsPage(BasePage):
    def run(self, state: dict) -> typing.Iterator[str | None]:
        yield "Running models..."
