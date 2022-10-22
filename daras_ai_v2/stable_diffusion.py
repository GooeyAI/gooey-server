import replicate


def inpainting(
    prompt: str,
    num_outputs: int,
    edit_image: str,
    mask: str,
    num_inference_steps: int,
) -> list[str]:
    model = replicate.models.get("devxpy/glid-3-xl-stable").versions.get(
        "d53d0cf59b46f622265ad5924be1e536d6a371e8b1eaceeebc870b6001a0659b"
    )
    return model.predict(
        prompt=prompt,
        num_outputs=num_outputs,
        edit_image=edit_image,
        mask=mask,
        num_inference_steps=num_inference_steps,
    )
