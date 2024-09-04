import gooey_gui as gui
from furl import furl
from daras_ai_v2 import settings


def prompting101():
    gui.markdown(
        """
        #### Prompting 101: 

        ###### Step 1: Create an idea or visualization in your mind. 
        `I want an image of an astronaut in a space suit walking on the streets of Mumbai.`
        """
    )
    gui.markdown(
        """
        ###### Step 2: Think about your descriptors and break it down as follows: 

        - What is the Medium of this image? \\
        eg. It is a painting, a sculpture, an old photograph, portrait, 3D render, etc.\n
        - What/Who are the Subject(s) or Main Object(s) in the image? \\
        eg. A human, an animal, an identity like gender, race, or occupation like dancer, astronaut etc. \n
        - What is the Style? \\
        eg. Is it Analogue photography, a watercolor, a line drawing, digital painting etc. \n
        - What are the Details? \\
        eg. facial features or expressions, the space and landscape, lighting or the colours etc. 
        """
    )
    gui.markdown(
        f"""
        ###### Step 3: Construct your prompt:
        `An analogue film still of an astronaut in a space suit walking on the busy streets of Mumbai, golden light on the astronaut, 4k`
        [example]({furl(settings.APP_BASE_URL).add(path='compare-ai-image-generators').add({"example_id": "s9nmzy34"}).url})
        """
    )
    gui.markdown(
        """
        You can keep editing your prompt until you have your desired output. Consider AI generators as a collaborative tool. 
        ##### What is the difference between Submit and Regenerate? 
        Each AI generation has a unique Seed number. A random seed is created when you initiate the first run on clicking the Submit button. The seed is maintained as you continue editing the image with different setting options on each subsequent Submit click.\n
        However, by clicking the Regenerate button, the AI will generate a new Seed and a completely new/different set of outputs.
        """
    )
