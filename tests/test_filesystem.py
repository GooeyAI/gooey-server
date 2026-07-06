from recipes.Filesystem import FilesystemPage


def test_get_tool_call_schema_exposes_command_only():
    schema = FilesystemPage.get_tool_call_schema({})
    assert set(schema.keys()) == {"command"}
    assert schema["command"]["type"] == "string"
