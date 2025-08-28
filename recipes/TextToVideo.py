import typing
from pydantic import BaseModel, Field

import gooey_gui as gui
from bots.models import Workflow
from daras_ai_v2.base import BasePage
from daras_ai_v2.enum_selector_widget import enum_multiselect
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
        "video",
    ]

    sane_defaults = {
        "duration": 8,
        "aspect_ratio": "16:9",
        "resolution": "1080p",
        "frames_per_second": 30,
        "camera_motion": "Auto",
        "use_audio_bed": True,
        "selected_models": [VideoGenerationModels.openai_sora.name],
    }

    class RequestModel(BasePage.RequestModel):
        text_prompt: str = Field(
            description="Describe your scene and optional look-and-feel. Choose one or more video models to compare"
        )

        # Video generation parameters
        duration: int = Field(
            default=8, ge=3, le=30, description="Duration of the video in seconds"
        )
        aspect_ratio: typing.Literal["16:9", "9:16", "1:1"] = Field(
            default="16:9", description="Video aspect ratio"
        )
        resolution: typing.Literal["720p", "1080p", "4K"] = Field(
            default="1080p", description="Video resolution"
        )
        frames_per_second: typing.Literal[24, 30, 60] = Field(
            default=30, description="Frames per second"
        )

        # Model selection
        selected_models: list[str] = Field(description="Video generation models to use")

        # Reference image
        reference_image: str | None = Field(
            default=None,
            description="Optional reference image for style or subject guidance",
        )

        # Style and creative controls
        style: str | None = Field(
            default=None, description="Optional style preset (e.g., cyberpunk noir, watercolor, Pixar-like)"
        )
        negative_prompt: str | None = Field(
            default=None, description="Things to avoid in the video generation"
        )
        camera_motion: typing.Literal["Auto", "Static", "Pan Left", "Pan Right", "Zoom In", "Zoom Out", "Dolly Forward", "Dolly Backward"] = Field(
            default="Auto", description="Camera movement pattern"
        )
        seed: int | None = Field(
            default=None, description="Random seed for reproducible results"
        )
        use_audio_bed: bool = Field(
            default=True, description="Use royalty-free ambient track"
        )

    class ResponseModel(BaseModel):
        output_videos: dict[str, HttpUrlStr] = Field(
            description="Generated videos for each selected model"
        )

    def run(self, state: dict) -> typing.Iterator[str | None]:
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

                # Enhance prompt with camera motion if specified
                enhanced_prompt = request.text_prompt
                if request.camera_motion and request.camera_motion != "Auto":
                    enhanced_prompt += f"; {request.camera_motion.lower()}"
                
                output_videos[selected_model] = generate_video(
                    model=model,
                    prompt=enhanced_prompt,
                    duration=request.duration,
                    reference_image=request.reference_image,
                    aspect_ratio=request.aspect_ratio,
                    resolution=request.resolution,
                    frames_per_second=request.frames_per_second,
                    style=request.style,
                    negative_prompt=request.negative_prompt,
                    seed=request.seed,
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
            raise UserError(
                "No videos were generated successfully. Please try again or select different models."
            )

        yield f"🎬 Generated {len(output_videos)} video(s) successfully!"

    def render_form_v2(self):
        # Main prompt text area
        gui.text_area(
            "🧠 **PROMPT**",
            key="text_prompt",
            placeholder="e.g., an atmospheric night-time city street in monsoon rain; slow dolly forward; neon reflections; cinematic lighting; end with a close-up of an umbrella",
            height=120,
        )
        gui.caption("Tip: Use short sentences and shot directions (camera, motion, framing). You can also add negative prompts in Settings.")
        
        # Optional image upload
        gui.write("🖼️ **OPTIONAL IMAGE**")
        gui.caption("Used for style or subject guidance")
        gui.file_uploader(
            "Drag & drop or click to upload",
            key="reference_image",
            accept=["png", "jpg", "jpeg"],
            help="PNG, JPG, up to 10 MB"
        )
        
        # Model selection with checkboxes
        gui.write("🧪 **COMPARE VIDEO MODELS**")
        gui.caption("Each selected model will render a separate video. Some models may be region- or access-restricted.")
        
        # Create model selection checkboxes
        col1, col2 = gui.columns(2)
        
        with col1:
            sora_checked = gui.checkbox("🔴 **Sora** limited access", key="__sora_selected", value=True)
            gui.caption("High-fidelity text→video. Great for complex scenes and long shots.")
            
            pika_checked = gui.checkbox("🟣 **Pika**", key="__pika_selected")  
            gui.caption("Fast iterations; strong stylization and motion dynamics.")
            
        with col2:
            veo3_checked = gui.checkbox("🔵 **Veo 3**", key="__veo3_selected")
            gui.caption("Cinematic look, strong prompt control and camera directions.")
            
            runway_checked = gui.checkbox("🟡 **Runway**", key="__runway_selected")
            gui.caption("Reliable visuals with editing tools in the broader ecosystem.")
        
        # Convert checkbox selections to selected_models list
        selected_models = []
        if sora_checked:
            selected_models.append(VideoGenerationModels.openai_sora.name)
        if veo3_checked:
            selected_models.append(VideoGenerationModels.google_veo_3.name)
        if pika_checked:
            selected_models.append(VideoGenerationModels.pika_labs.name)
        if runway_checked:
            selected_models.append(VideoGenerationModels.runway_gen_3.name)
            
        gui.session_state["selected_models"] = selected_models or [VideoGenerationModels.openai_sora.name]
        
        gui.caption("Confused about model differences? See our [prompt & model guide](#).")

    def validate_form_v2(self):
        assert gui.session_state.get("text_prompt", "").strip(), "Please enter a video prompt"
        assert gui.session_state.get("selected_models"), "Please select at least one video model"

    def render_settings(self):
        gui.write("⚙️ **SETTINGS**")
        
        # Top row: Duration and Aspect Ratio
        col1, col2 = gui.columns(2)
        with col1:
            gui.selectbox(
                "**Duration**",
                options=[3, 5, 8, 10, 15, 20, 30],
                format_func=lambda x: f"{x}s",
                key="duration",
            )
        
        with col2:
            gui.selectbox(
                "**Aspect Ratio**",
                options=["16:9", "9:16", "1:1"],
                key="aspect_ratio",
            )
        
        # Second row: Resolution and Frames per Second
        col3, col4 = gui.columns(2)
        with col3:
            gui.selectbox(
                "**Resolution**",
                options=["720p", "1080p", "4K"],
                key="resolution",
            )
        
        with col4:
            gui.selectbox(
                "**Frames per Second**",
                options=[24, 30, 60],
                format_func=lambda x: f"{x}",
                key="frames_per_second",
            )
        
        # Style Preset
        gui.text_area(
            "**Style Preset** _(optional)_",
            key="style",
            placeholder="e.g., cyberpunk noir, watercolor, Pixar-like, Wes Anderson, anime",
            height=80,
        )
        
        # Negative Prompt
        gui.text_area(
            "**Negative Prompt** _(things to avoid)_",
            key="negative_prompt", 
            placeholder="e.g., text artifacts, extra limbs, flicker, low contrast",
            height=80,
        )
        
        # Bottom row: Camera Motion and Seed
        col5, col6 = gui.columns(2)
        with col5:
            gui.selectbox(
                "**Camera Motion**",
                options=["Auto", "Static", "Pan Left", "Pan Right", "Crane Up", "Dolly In", "Dolly Out"],
                key="camera_motion",
            )
        
        with col6:
            gui.text_input(
                "**Seed**",
                key="seed",
                placeholder="random",
                help="Enter a number for reproducible results"
            )
        
        # Use audio bed checkbox
        gui.checkbox(
            "**Use audio bed** _(royalty-free ambient track)_",
            key="use_audio_bed",
            value=True
        )
        
        gui.caption("*4K availability varies by model. Longer durations and higher resolutions increase cost and render time.")

    def render_output(self):
        output_videos = gui.session_state.get("output_videos", {})
        
        if not output_videos:
            gui.write("#### 🎬 RESULTS")
            gui.write("Videos will appear here after generation...")
            return
        
        gui.write("#### 🎬 RESULTS")
        
        # Create 2x2 grid for video results
        if len(output_videos) <= 2:
            cols = gui.columns(2)
        else:
            cols = gui.columns(2)  # Keep 2x2 grid even for 3-4 videos
        
        for i, (model_name, video_url) in enumerate(output_videos.items()):
            model = VideoGenerationModels[model_name]
            col_idx = i % 2
            
            with cols[col_idx]:
                # Model status card
                status_colors = {
                    VideoGenerationModels.openai_sora.name: "🔴",
                    VideoGenerationModels.google_veo_3.name: "🔵", 
                    VideoGenerationModels.pika_labs.name: "🟣",
                    VideoGenerationModels.runway_gen_3.name: "🟡"
                }
                
                status_color = status_colors.get(model_name, "⚪")
                gui.write(f"{status_color} **{model.value.split(' (')[0]}** ready")
                
                if video_url:
                    gui.video(video_url, autoplay=False, show_download_button=True)
                    gui.caption("~8s • 1080p • 30fps")
                else:
                    gui.write("🔄 Processing...")
                    
                gui.write("---")  # Separator between videos

    def get_raw_price(self, state: dict) -> int:
        selected_models = state.get("selected_models", [])
        duration = state.get("duration", 8)
        resolution = state.get("resolution", "1080p")
        frames_per_second = state.get("frames_per_second", 30)

        total_credits = 0

        for model_name in selected_models:
            # Base pricing per model (approximate credits)
            model = VideoGenerationModels[model_name]
            base_cost = self._get_model_base_cost(model)

            # Duration multiplier (longer videos cost more)
            duration_multiplier = duration / 8  # Base duration is 8 seconds

            # Resolution multiplier
            resolution_multiplier = self._get_resolution_multiplier(resolution)

            # FPS multiplier
            fps_multiplier = frames_per_second / 30  # Base FPS is 30

            model_cost = (
                base_cost * duration_multiplier * resolution_multiplier * fps_multiplier
            )
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

    def _get_resolution_multiplier(self, resolution: str) -> float:
        """Get cost multiplier based on resolution"""
        resolution_multipliers = {
            "720p": 0.8,
            "1080p": 1.0,  # Base resolution
            "4K": 2.5,  # Much higher cost for 4K
        }
        return resolution_multipliers.get(resolution, 1.0)

    @classmethod
    def get_example_preferred_fields(cls, state: dict) -> list[str]:
        return ["text_prompt", "selected_models", "duration", "aspect_ratio", "resolution"]

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

    def _render_header(self):
        from widgets.workflow_image import CIRCLE_IMAGE_WORKFLOWS
        from widgets.base_header import render_header_title, render_breadcrumbs_with_author
        from daras_ai_v2.breadcrumbs import get_title_breadcrumbs
        from widgets.author import render_author_from_workspace
        from routers.root import RecipeTabs

        sr, pr = self.current_sr_pr
        is_example = pr.saved_run == sr
        tbreadcrumbs = get_title_breadcrumbs(self, sr, pr, tab=self.tab)
        can_save = self.can_user_save_run(sr, pr)
        request_changed = self._has_request_changed()

        if self.tab != RecipeTabs.run and self.tab != RecipeTabs.preview:
            # Examples, API, Saved, etc
            if self.tab == RecipeTabs.saved or self.tab == RecipeTabs.history:
                with gui.div(className="mb-2"):
                    render_author_from_workspace(self.current_workspace)
            with gui.div(className="mb-2"):
                render_header_title(tbreadcrumbs)
                # Add description for non-run tabs too
                with gui.div(className="mt-2"):
                    gui.caption(
                        "Describe your scene and optional look-and-feel. Choose one or more video models to compare (Sora, Veo 3, Pika, Runway). Add an optional reference image for style or subject. Click Run to generate videos on the right. Adjust your prompt or settings and run again to iterate fast."
                    )
        else:
            # Run tab
            img_style = dict(objectFit="cover", marginBottom=0)
            if self.workflow in CIRCLE_IMAGE_WORKFLOWS:
                img_style["borderRadius"] = "50%"
            else:
                img_style["borderRadius"] = "12px"

            with gui.div(className="d-flex gap-4 w-100 mb-2"):
                if pr.photo_url:
                    with gui.div(className="d-none d-md-inline"):
                        gui.image(
                            src=pr.photo_url,
                            style=img_style | dict(width="96px", height="96px"),
                        )

                # desktop image and title, social buttons, extra and breadcrumbs
                with gui.div(className="w-100 d-flex flex-column gap-2"):
                    with gui.div(className="d-flex align-items-start w-100 my-auto"):
                        if pr.photo_url:
                            with gui.div(className="d-inline d-md-none me-2"):
                                gui.image(
                                    src=pr.photo_url,
                                    style=img_style | dict(width="56px", height="56px"),
                                )

                        with gui.div(
                            className="d-flex justify-content-between w-100 align-items-start my-auto"
                        ):
                            with gui.div(className="w-100"):
                                render_header_title(tbreadcrumbs)
                                # Add description right below title
                                with gui.div(className="mt-2"):
                                    gui.caption(
                                        "Describe your scene and optional look-and-feel. Choose one or more video models to compare (Sora, Veo 3, Pika, Runway). Add an optional reference image for style or subject. Click Run to generate videos on the right. Adjust your prompt or settings and run again to iterate fast."
                                    )

                            with gui.div(
                                className="d-flex align-items-end flex-column-reverse gap-2",
                                style={"whiteSpace": "nowrap"},
                            ):
                                if request_changed or (can_save and not is_example):
                                    self._render_unpublished_changes_indicator()
                                self.render_social_buttons()

                    with gui.div(
                        className="d-flex align-items-center gap-2 w-100 flex-wrap"
                    ):
                        self.render_header_extra()
                        render_breadcrumbs_with_author(
                            tbreadcrumbs,
                            user=self.current_sr_user,
                            pr=self.current_pr,
                            sr=self.current_sr,
                            current_workspace=(
                                self.is_logged_in() and self.current_workspace or None
                            ),
                        )

        if self.tab == RecipeTabs.run and is_example:
            with gui.div(className="container-margin-reset"):
                if self.current_pr and self.current_pr.notes:
                    gui.write(self.current_pr.notes, line_clamp=3)

    def render_description(self):
        gui.markdown(
            """
            Describe your scene and optional look-and-feel. Choose one or more video models to compare (Sora, Veo 3, Pika, Runway). Add an optional reference image for style or subject. Click Run to generate videos on the right. Adjust your prompt or settings and run again to iterate fast.
            """
        )

    def render_usage_guide(self):
        gui.markdown(
            """
            ### 🎬 How to Create Great AI Videos
            
            **✨ Prompt Tips:**
            - Describe subject, setting, and mood first
            - Add camera moves (e.g., dolly in, pan left)
            - Specify timing for beats: "end on a close-up"
            
            **📱 Best Practices:**
            - Use short sentences and clear directions
            - Try different models for varied styles
            - Iterate with negative prompts to refine results
            """
        )

    def additional_notes(self):
        return """
*4K availability varies by model. Longer durations and higher resolutions increase cost and render time.

By running, you agree to Gooey.AI's terms & privacy policy. This workflow enforces provider safety filters. Do not upload personal images without permission.
        """.strip()
