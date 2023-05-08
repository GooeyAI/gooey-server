from pydantic import BaseModel

from daras_ai_v2.language_model import ConversationEntry


class PromptTreeNode(BaseModel):
    prompt: str | list[ConversationEntry]
    children: list["PromptTreeNode"]


PromptTree = list[PromptTreeNode]
