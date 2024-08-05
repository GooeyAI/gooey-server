from gooey_sdk import GooeyAi

gooey = GooeyAi()
meta, response = gooey.ask_copilot(
  input_prompt = "What is the meaning of life?",
  bot_script = "You are Marvin, the Paranoid Android. You are here to assist passing hitchhikers.",
  input_documents = "sdk/resources/documents",
  selected_model = "mixtral_8x7b_instruct_0_1"
)

print("Response: ", response.output_text)
print(response)