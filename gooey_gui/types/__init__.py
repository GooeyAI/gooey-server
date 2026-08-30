import pydantic


class StrictComponentModel(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="forbid", strict=True)
