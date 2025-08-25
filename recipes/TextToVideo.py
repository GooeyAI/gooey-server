import typing
from pydantic import BaseModel, Field

import gooey_gui as gui
from bots.models import Workflow
from daras_ai_v2.base import BasePage
from daras_ai_v2.exceptions import UserError
from daras_ai_v2.pydantic_validation import HttpUrlStr
from daras_ai_v2.safety_checker import safety_checker
from daras_ai_v2.video_generation import VideoGenerationModels, generate_video
from daras_ai_v2.variables_widget import render_prompt_vars


class TextToVideoPage(BasePage):
    title = "Text Video"
    explore_image = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/text-video-hero.png"
    workflow = Workflow.TEXT_VIDEO
    slug_versions = [
        "TextToVideo",
        "text-to-video", 
        "text-video",
        "video-generation",
    ]

    sane_defaults = {
        "duration": 5,
        "aspect_ratio": "16:9",
        "quality": "standard",
        "selected_models": [VideoGenerationModels.openai_sora.name],
    }

    class RequestModel(BasePage.RequestModel):
        text_prompt: str = Field(
            description="Describe your scene and optional look-and-feel. Choose one or more video models to compare"
        )
        negative_prompt: str | None = Field(
            default=None,
            description="What to avoid in the video generation"
        )
        
        # Video generation parameters
        duration: int = Field(
            default=5,
            ge=3,
            le=10,
            description="Duration of the video in seconds (3-10)"
        )
        aspect_ratio: typing.Literal["16:9", "9:16", "1:1"] = Field(
            default="16:9",
            description="Video aspect ratio"
        )
        quality: typing.Literal["standard", "high"] = Field(
            default="standard",
            description="Generation quality"
        )
        
        # Model selection
        selected_models: list[str] = Field(
            description="Video generation models to use"
        )
        
        # Reference image
        reference_image: str | None = Field(
            default=None,
            description="Optional reference image for style or subject guidance"
        )
        
        # Style and creative controls
        style: str | None = Field(
            default=None,
            description="Optional style parameter for certain models"
        )
        seed: int | None = Field(
            default=None,
            description="Random seed for reproducible results"
        )

    class ResponseModel(BaseModel):
        output_videos: dict[str, HttpUrlStr] = Field(
            description="Generated videos for each selected model"
        )

    def run(self, state: dict) -> typing.Iterator[str | None]:
        """
        Main execution method for text-to-video generation.
        Generates videos using the selected models without UI components.
        """
        request: TextToVideoPage.RequestModel = self.RequestModel.model_validate(state)
        
        # Render any template variables in the prompt
        request.text_prompt = render_prompt_vars(request.text_prompt, state)
        
        # Safety check if not disabled
        if not self.request.user.disable_safety_checker:
            yield "Running safety checker..."
            safety_checker(text=request.text_prompt)
        
        # Initialize output storage
        state["output_videos"] = output_videos = {}
        
        # Generate videos for each selected model
        for selected_model in request.selected_models:
            try:
                model = VideoGenerationModels[selected_model]
                yield f"Generating video with {model.value}..."
                
                output_videos[selected_model] = generate_video(
                    model=model,
                    prompt=request.text_prompt,
                    duration=request.duration,
                    reference_image=request.reference_image,
                    aspect_ratio=request.aspect_ratio,
                    style=request.style,
                    negative_prompt=request.negative_prompt,
                    seed=request.seed,
                    quality=request.quality,
                )
                
                yield f"✅ Completed {model.value}"
                
            except Exception as e:
                # Log error but continue with other models
                error_msg = f"❌ Error with {model.value}: {str(e)}"
                yield error_msg
                
                # Optionally skip this model and continue
                if len(request.selected_models) == 1:
                    # If only one model, raise the error
                    raise UserError(f"Video generation failed: {str(e)}") from e
                else:
                    # Continue with other models
                    continue
        
        if not output_videos:
            raise UserError("No videos were generated successfully. Please try again or select different models.")
        
        yield f"🎬 Generated {len(output_videos)} video(s) successfully!"

    def get_raw_price(self, state: dict) -> int:
        """
        Calculate pricing based on selected models and parameters.
        Using 1.3x pricing multiplier as mentioned in the requirements.
        """
        selected_models = state.get("selected_models", [])
        duration = state.get("duration", 5)
        quality = state.get("quality", "standard")
        
        total_credits = 0
        
        for model_name in selected_models:
            # Base pricing per model (approximate credits)
            model = VideoGenerationModels[model_name]
            base_cost = self._get_model_base_cost(model)
            
            # Duration multiplier (longer videos cost more)
            duration_multiplier = duration / 5  # Base duration is 5 seconds
            
            # Quality multiplier
            quality_multiplier = 1.5 if quality == "high" else 1.0
            
            model_cost = base_cost * duration_multiplier * quality_multiplier
            total_credits += model_cost
        
        # Apply 1.3x pricing multiplier as specified
        return int(total_credits * 1.3)

    def _get_model_base_cost(self, model: VideoGenerationModels) -> int:
        """Get base cost in credits for each model"""
        base_costs = {
            VideoGenerationModels.openai_sora: 50,  # Higher cost for premium models
            VideoGenerationModels.google_veo_3: 45,
            VideoGenerationModels.runway_gen_3: 40,
            VideoGenerationModels.pika_labs: 35,
        }
        return base_costs.get(model, 40)  # Default cost

    def get_example_preferred_fields(cls, state: dict) -> list[str]:
        return ["selected_models", "duration", "aspect_ratio"]

    def related_workflows(self) -> list:
        from recipes.Lipsync import LipsyncPage
        from recipes.DeforumSD import DeforumSDPage
        from recipes.CompareText2Img import CompareText2ImgPage
        from recipes.VideoBots import VideoBotsPage

        return [
            LipsyncPage,
            DeforumSDPage,
            CompareText2ImgPage,
            VideoBotsPage,
        ]

    def render_description(self):
        gui.markdown(
            """
            Generate high-quality videos from text descriptions using state-of-the-art AI models. 
            Compare outputs from multiple video generation models including Sora, Veo 3, Runway, and Pika.
            
            Perfect for creating marketing content, social media videos, creative projects, and prototyping video concepts.
            """
        )

    def additional_notes(self):
        return """
Video generation is a resource-intensive process that may take several minutes to complete.
Higher quality and longer duration videos will incur additional costs.
For best results, use descriptive prompts with specific camera movements, lighting, and scene details.
        """.strip()
