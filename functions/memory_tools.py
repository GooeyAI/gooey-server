from __future__ import annotations
import typing


from functions.models import FunctionScopes
from functions.base_llm_tool import (
    BaseLLMTool,
)
from memory.models import MemoryEntry

if typing.TYPE_CHECKING:
    pass


class GooeyMemoryLLMTool(BaseLLMTool):
    scope: FunctionScopes | None
    memory_entry: MemoryEntry

    def bind(self, memory_entry: MemoryEntry):
        self.memory_entry = memory_entry
        return self


class GooeyMemoryLLMToolRead(GooeyMemoryLLMTool):
    name = "GOOEY_MEMORY_READ_VALUE"

    def __init__(self, scope: FunctionScopes | None):
        self.scope = scope
        super().__init__(
            name=self.name,
            label="Read Value from Gooey.AI Memory",
            description="Read the value of a key from the Gooey.AI store.",
            properties={
                "key": {
                    "type": "string",
                    "description": "The key to read from the Gooey.AI store.",
                },
            },
            required=["key"],
        )

    def call(self, key: str) -> dict:
        try:
            value = MemoryEntry.objects.get(
                user_id=self.memory_entry.user_id, key=key
            ).value
        except MemoryEntry.DoesNotExist:
            return {"success": False, "error": f"Key not found: {key}"}
        return {"success": True, "key": key, "value": value}


class GooeyMemoryLLMToolWrite(GooeyMemoryLLMTool):
    name = "GOOEY_MEMORY_WRITE_VALUE"

    def __init__(self, scope: FunctionScopes):
        self.scope = scope
        super().__init__(
            name=self.name,
            label="Write Value to Gooey.AI Memory",
            description="Write a value to the Gooey.AI store.",
            properties={
                "key": {
                    "type": "string",
                    "description": "The key to write to the Gooey.AI store.",
                },
                "value": {
                    "type": "string",
                    "description": "The value to write to the Gooey.AI store.",
                },
            },
            required=["key", "value"],
        )

    def call(self, key: str, value) -> dict:
        self.memory_entry.write(key, value)
        return {"success": True}


class GooeyMemoryLLMToolDelete(GooeyMemoryLLMTool):
    name = "GOOEY_MEMORY_DELETE_VALUE"

    def __init__(self, scope: FunctionScopes):
        self.scope = scope
        super().__init__(
            name=self.name,
            label="Delete Value from Gooey.AI Memory",
            description="Delete a value from the Gooey.AI store.",
            properties={
                "key": {
                    "type": "string",
                    "description": "The key to delete from the Gooey.AI store.",
                },
            },
            required=["key"],
        )

    def call(self, key: str) -> dict:
        MemoryEntry.objects.filter(user_id=self.memory_entry.user_id, key=key).delete()
        return {"success": True}
