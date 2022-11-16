var foor =
{
name: "Email of you in Paris",
inputs: [
    {input: "Email", sample: "sean@dara.network"},
    {input: "prompt", sample: "Person as Santa's elf"} ],
    steps: [
        {model:PHOTO_FROM_EMAIL, provider: APOLLO},
        {model:MASK_FACE, settings: {X: 0, Y: 20, zoom: 10 },
        {model:INPAINT, provider:SD_v15},
        {model:REFINE_FACE, provider:GFPGAN},
        {model:SEND_EMAIL, provider:AWS, to:Email, from:"support@gooey.ai"},
    ]
};