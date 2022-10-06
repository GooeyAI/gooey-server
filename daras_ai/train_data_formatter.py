import ast

import parse
import streamlit as st
from glom import glom
from html2text import html2text

from daras_ai.core import daras_ai_step

input_spec_parse_pattern = "{" * 5 + "}" * 5


@daras_ai_step("Training data extractor")
def train_data_formatter(idx, variables, state):
    input_var = st.text_input(
        label="Input data var",
        value=state.get("input_var", None),
    )
    if input_var is None:
        return
    state.update({"input_var": input_var})
    input_json = variables[input_var]

    input_format = st.text_area(
        label="Prompt template",
        value=state.get("input_format", ""),
    )
    state.update({"input_format": input_format})

    output_format = st.text_area(
        label="Completion template",
        value=state.get("output_format", ""),
    )
    state.update({"output_format": output_format})

    do_html2text = st.checkbox(
        "HTML -> Text",
        value=state.get("do_html2text", False),
    )
    state.update({"do_html2text": do_html2text})

    input_prompts = []
    input_spec_results: list[parse.Result] = list(
        parse.findall(input_spec_parse_pattern, input_format)
    )
    for spec_result in input_spec_results:
        spec = spec_result.fixed[0]
        input_values = glom(input_json, ast.literal_eval(spec))
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
        examples = glom(input_json, ast.literal_eval(spec))
        for prompt, completion_or_list in zip(input_prompts, examples):
            if isinstance(completion_or_list, list):
                for it in completion_or_list:
                    append_training_data(prompt, it)
            elif completion_or_list:
                append_training_data(prompt, completion_or_list)

    "**Training data**"
    st.dataframe(training_data)

    out_var = st.text_input(
        label="Training Output var",
        value=state.get("out_var"),
    )
    if out_var is not None:
        state.update({"out_var": out_var})
        variables[out_var] = training_data

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


def format_input_var(input_var, variables):
    input_spec_results: list[parse.Result] = list(
        parse.findall(input_spec_parse_pattern, input_var)
    )
    for spec_result in input_spec_results:
        spec = spec_result.fixed[0]
        variable_value = glom(variables, ast.literal_eval(spec))
        input_var = input_var.replace("{{" + spec + "}}", variable_value)
    return input_var
