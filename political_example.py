import ast
import json
import random

import openai
import parse
import requests
import streamlit as st
from decouple import config
from glom import glom
from html2text import html2text

st.set_page_config(layout="wide")

"# Drag & Drop AI - Political letters example"

col1, col2 = st.columns(2)

with col1:
    with st.expander("Data source API"):
        request_method = st.text_input(
            label="HTTP method",
            value="POST",
        )
        request_url = st.text_input(
            label="URL", value="https://www.takeaction.network/graphql"
        )
        request_headers = st.text_area(
            label="Headers",
            value='{"graphql_key": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJTZWFuIEJsYWdzdmVkdCIsInBlcm1pc3Npb25zIjpbInRhbGtpbmdfcG9pbnRzIl0sImV4cCI6MTY2NTM0NTU0N30.GI_x7-MLGJ1pSSP5-EJ36iOMIz7C-bDVLGTIdOhvhhI"}',
        )
        json_data = st.text_area(
            label="JSON body",
            value='{"query": "{billTrackers {bill {title year url billNumber} talkingPoints xactions {id script script1 script2}}}"}',
        )

        "**Response**"

        with st.spinner():
            r = requests.request(
                request_method,
                request_url,
                headers=json.loads(request_headers),
                json=json.loads(json_data),
            )
        r.raise_for_status()
        response_json = r.json()
        st.write(response_json)

    with st.expander("Data extractor"):

        input_format = st.text_area(
            label="Prompt template",
            value="""\
billNumber: {{ ("data.billTrackers", ["bill.billNumber"]) }}
billTitle: {{ ("data.billTrackers", ["bill.title"]) }}
billURL: {{ ("data.billTrackers", ["bill.url"]) }}
talkingPoints: {{ ("data.billTrackers", ["talkingPoints"]) }}\
        """,
        )

        output_format = st.text_area(
            label="Completion template",
            value='{{ ("data.billTrackers", [("xactions", ["script"])]) }}',
        )

        do_html2text = st.checkbox("HTML -> Text", value=True)

        input_spec_parse_pattern = "{" * 5 + "}" * 5

        input_prompts = []
        input_spec_results: list[parse.Result] = list(
            parse.findall(input_spec_parse_pattern, input_format)
        )
        for spec_result in input_spec_results:
            spec = spec_result.fixed[0]
            input_values = glom(response_json, ast.literal_eval(spec))
            for i, prompt in enumerate(input_values):
                if not prompt:
                    continue
                prompt = str(prompt)
                if do_html2text:
                    prompt = html2text(prompt)
                prompt = prompt.strip()
                try:
                    existing = input_prompts[i]
                except IndexError:
                    input_prompts.insert(i, input_format)
                    existing = input_format
                input_prompts[i] = existing.replace("{{" + spec + "}}", prompt)

        def append_training_data(prompt, completion):
            if not completion or not prompt:
                return

            # add header to prompt
            # prompt = prompt_header.strip() + "\n\n" + prompt

            # # See - https://beta.openai.com/docs/guides/fine-tuning/data-formatting
            # #   Each prompt should end with a fixed separator to inform the model
            # #   when the prompt ends and the completion begins.
            # #   A simple separator which generally works well is \n\n###\n\n.
            # prompt += "\n\n####\n\n"

            completion = str(completion)
            if do_html2text:
                completion = html2text(completion)
            completion = completion.strip()

            # # Each completion should start with a whitespace due to our tokenization,
            # # which tokenizes most words with a preceding whitespace.
            # completion = " " + completion + "####"

            training_data.append({"prompt": prompt, "completion": completion})

        training_data = []
        output_spec_results: list[parse.Result] = list(
            parse.findall(input_spec_parse_pattern, output_format)
        )
        for spec_result in output_spec_results:
            spec = spec_result.fixed[0]
            examples = glom(response_json, ast.literal_eval(spec))
            for prompt, completion_or_list in zip(input_prompts, examples):
                if isinstance(completion_or_list, list):
                    for it in completion_or_list:
                        append_training_data(prompt, it)
                elif completion_or_list:
                    append_training_data(prompt, completion_or_list)

        "**Training data**"
        st.dataframe(training_data)

        # openai.FineTune

        # with open("training_data.jsonl", "a") as f:
        #     for item in training_data:
        #         json.dump(training_data, f)
        # with tempfile.NamedTemporaryFile("w+", suffix=".json") as f:
        #     json.dump(training_data, f)
        #     print(
        #         subprocess.check_output(
        #             [
        #                 sys.executable,
        #                 "-m",
        #                 "openai",
        #                 "tools",
        #                 "fine_tunes.prepare_data",
        #                 "-f",
        #                 f.name,
        #             ]
        #         )
        #     )

    with st.expander("Text API selection"):
        # select text api
        selected_text_api = st.selectbox("Text API", ["openai", "goose.ai"], 0)

        # set api key
        match selected_text_api:
            case "openai":
                openai.api_key = config("OPENAI_API_KEY")
            case "goose.ai":
                openai.api_base = "https://api.goose.ai/v1"

        # list engines
        with st.spinner():
            engines = openai.Engine.list()

        # select engine
        engine_choices = [engine["id"] for engine in engines["data"]]
        selected_engine = st.selectbox(
            "Engine", engine_choices, index=engine_choices.index("text-davinci-002")
        )

    with st.expander("Prompt generation"):
        prompt_header = st.text_area(
            label="Prompt header",
            value="A polite and passionate writer that argues to politicians from a voter’s perspective as to why they should support or vote against upcoming Bills. It often deviates from the talking points to make a grounded, personal argument regarding why the elected representative should work for or against an upcoming Bill",
        )
        prompt_sep = st.text_input("Prompt end separator", value="\n$$$$\n")
        completion_sep = st.text_input("Completion end separator", value="\n####\n")
        n_prompts = st.number_input("Number of examples", value=5)
        max_tokens = st.number_input("Max output tokens", value=128)

        text_prompt = prompt_header.strip() + "\n\n"
        for eg in random.choices(training_data, k=n_prompts):
            text_prompt += eg["prompt"] + prompt_sep + eg["completion"] + completion_sep

example_prompt = """\
billNumber: 5188
billTitle: Concerning the creation of the Washington state public bank.
billURL: https://app.leg.wa.gov/billsummary?BillNumber=5188&Year;=2021&Initiative;=false
talkingPoints: Senate Summary

  * Activates a public financial cooperative as a cooperative membership organization to lend to local and tribal governmental entities.
  * Local and tribal governments, along with the state, are permitted to be members of the public financial cooperative.
  * Enables the public financial cooperative to issue debt in the name of the cooperative rather than the state of Washington.\
"""

with col2:
    "### Prompt"

    eg = random.choice(training_data)
    example_prompt = st.text_area("Example prompt", value=example_prompt)
    text_prompt += example_prompt + prompt_sep

    with st.expander("Final Prompt"):
        st.text(text_prompt)

    "### Completion"

    with st.spinner():
        r = openai.Completion.create(
            engine=selected_engine,
            max_tokens=max_tokens,
            prompt=text_prompt,
            stop=[completion_sep],
        )

    # choose the first completion that isn't empty
    response = ""
    for choice in r["choices"]:
        text = choice["text"].strip()
        if text:
            response = text
            break

    st.text(response)
