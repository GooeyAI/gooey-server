from daras_ai_v2.slack_bot import safe_channel_name


def test_slack_safe_channel_name():
    assert safe_channel_name("hello world!") == "hello-world"
    assert safe_channel_name("My, Awesome, Channel %") == "my-awesome-channel"
