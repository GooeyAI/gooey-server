import typing

import gooey_gui as gui

from daras_ai_v2 import icons
from daras_ai_v2.copy_to_clipboard_button_widget import copy_to_clipboard_button
from functions.inbuilt_tools import FeedbackCollectionLLMTool, CallTransferLLMTool


class Prompt(typing.NamedTuple):
    title: str
    snippet: str


PROMPT_LIBRARY = [
    Prompt(
        title="Web Search Tool",
        snippet="""
## Web

Use the google search tool to access up-to-date information from the web or when responding to the user requires information about upcoming events or their location. \
Provide link(s) to relevant sources. Some examples of when to use this tool include:

- Local Information: Use the google search tool to respond to questions that require information about the user's location, such as the weather, local businesses, or events.
- Freshness: If up-to-date information on a topic could potentially change or enhance the answer, call the google search tool any time you would otherwise refuse to answer a question because your knowledge might be out of date.
- Niche Information: If the answer would benefit from detailed information not widely known or understood (which might be found on the internet), use web sources directly rather than relying on the distilled knowledge from pretraining.
- Accuracy: If the cost of a small mistake or outdated information is high (e.g., using an outdated version of a software library or not knowing the date of the next game for a sports team), then use the google search tool.
- When asked: If it's implied or you are asked to search the web, use the google search tool.
- Unknown Information: If you don't know the answer to a question, then use google search tool.
        """.strip(),
    ),
    Prompt(
        title="Follow-up Question Buttons",
        snippet="""
After your response, always display relevant follow-up questions the user is likely to ask as HTML buttons (but do not repeat follow-up questions). \
This allows the user to ask follow-up questions to refine the search. This mode is particularly useful for complex queries that require detailed answers. \
Try not to repeat follow-up questions you displayed earlier in the conversation.

{% if platform == "WHATSAPP" %}
First display the questions to the user as plain text (with an appropriate emoji in front)
{emoji1} {question1}
{emoji2} {question2}
{emoji3} {question3}
Then render quick buttons as HTML elements like so: 
{% else %}
Display the questions to the user as HTML elements like so: 
{% endif %}
<button gui-target="input_prompt">{emoji1} {question1}</button>
<button gui-target="input_prompt">{emoji2} {question2}</button> 
<button gui-target="input_prompt">{emoji3} {question3}</button>
        """.strip(),
    ),
    Prompt(
        title="Location Button",
        snippet="""
If the user asks something related to their current location, ask them for their location first by displaying the following html button: <button gui-action="send_location"></button>
Explain your need for the location and comfort the user in knowing that their location wont be shared publicly as a binding legal agreement. \
If the geocoding response could not be retrieved, ask the user to share the name of their city or area (or guess it from the coordinates if provided). \
Use the geocoding response to lookup details on google instead of location coordinates
        """.strip(),
    ),
    Prompt(
        title="Twilio Call Transfer Tool",
        snippet=CallTransferLLMTool.system_prompt,
    ),
    Prompt(
        title="Feedback Collection Tool",
        snippet=FeedbackCollectionLLMTool.system_prompt,
    ),
    Prompt(
        title="Current Date",
        snippet="Current date: {{ datetime.utcnow }}",
    ),
    Prompt(
        title="JS code interpreter",
        snippet="""
## Code

As an advanced language model, you can generate javascript code and execute it using the provided javascript code interpreter. \
Don't display the javascript code, instead use the provided tool to execute the code directly. Some examples of when to use this tool include:

- Making external web requests and API calls using browser fetch() API. You are allowed to make calls to any API out there. If the API requires credentials, try it anyway. If it fails, ask the user for the required credentials.
- Maths: Doing any numerical computation or mathematical operations like arithmetic, prefer using javascript instead of doing it manually. More examples include timezone conversions, counting, comparisons, algebra
- Doing data analysis and visualization
- Converting files between formats
        """.strip(),
    ),
]


def render_prompt_library():
    with gui.expander(f"{icons.library} Prompt Library", key="prompt_library_expander"):
        if not gui.session_state.get("prompt_library_expander"):
            return

        for prompt in PROMPT_LIBRARY:
            copy_to_clipboard_button(
                label=f"{icons.copy_solid} {prompt.title}",
                value=prompt.snippet,
                type="tertiary",
            )
