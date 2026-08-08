-- Live Activity: the raw user-interaction feed across every surface.
--
-- Metabase setup:
--   * Field filter {{created_at}} -> bots_savedrun.created_at (default: Previous 24 hours)
--   * Field filter {{surface}}    -> bots_savedrun.surface (optional)
--   * Set the "URL" column's display type to Link.
--   * Dashboard auto-refresh floor is 1 minute (see README).
--
-- Cheap by design: no JSONB unnesting, only a couple of scalar `->>` lookups,
-- so it is safe to re-run on a refresh timer.

with workflow_names (workflow, workflow_name, slug) as (
    values
        (1, 'Doc Search', 'doc-search'),
        (2, 'Doc Summary', 'doc-summary'),
        (3, 'Google GPT', 'google-gpt'),
        (4, 'Agent', 'agent'),
        (5, 'Lipysnc + TTS', 'lipsync-maker'),
        (6, 'Text to Speech', 'compare-text-to-speech-engines'),
        (7, 'Speech Recognition', 'speech'),
        (8, 'Lipsync', 'Lipsync'),
        (9, 'Deforum Animation', 'animation-generator'),
        (10, 'Compare Text2Img', 'compare-ai-image-generators'),
        (11, 'Text2Audio', 'text2audio'),
        (12, 'Img2Img', 'ai-photo-editor'),
        (13, 'Face Inpainting', 'face-in-ai-generated-photo'),
        (14, 'Google Image Gen', 'render-images-with-ai'),
        (15, 'Compare AI Upscalers', 'compare-ai-upscalers'),
        (16, 'SEO Summary', 'seo-paragraph-generator'),
        (17, 'Email Face Inpainting', 'ai-image-from-email-lookup'),
        (18, 'Social Lookup Email', 'email-writer-with-profile-lookup'),
        (19, 'Object Inpainting', 'product-photo-background-generator'),
        (20, 'Image Segmentation', 'remove-image-background-with-ai'),
        (21, 'Compare LLM', 'compare-large-language-models'),
        (22, 'Chyron Plant', 'ChyronPlant'),
        (23, 'Letter Writer', 'LetterWriter'),
        (24, 'Smart GPT', 'SmartGPT'),
        (25, 'AI QR Code', 'qr-code'),
        (26, 'Doc Extract', 'doc-extract'),
        (27, 'Related QnA Maker', 'related-qna-maker'),
        (28, 'Related QnA Maker Doc', 'related-qna-maker-doc'),
        (29, 'Embeddings', 'text-embedings'),
        (30, 'Bulk Runner', 'bulk'),
        (31, 'Bulk Evaluator', 'eval'),
        (32, 'Functions', 'functions'),
        (33, 'Translation', 'compare-ai-translation'),
        (34, 'Model Trainer', 'model-trainer'),
        (35, 'Video Generation', 'video')
),

surface_names (surface, surface_name) as (
    values
        (0, 'Run'), (1, 'API'), (2, 'Deployment'), (3, 'Ask Prompt'),
        (4, 'Ask'), (5, 'Tool Call'), (6, 'Internal'), (7, 'Analysis'),
        (8, 'Export'), (9, 'Bulk')
)

select
    sr.created_at,
    case
        when sr.error_msg <> '' then '❌ Error'
        when sr.run_status <> '' then '⏳ ' || sr.run_status
        else '✅ Done'
    end                                            as status,
    coalesce(nullif(u.display_name, ''), u.email, u.phone_number, sr.uid) as "user",
    coalesce(nullif(w.name, ''), 'Personal')       as workspace,
    sn.surface_name                                as surface,
    wn.workflow_name                               as workflow,
    left(sr.state ->> 'input_prompt', 200)         as prompt,
    sr.run_time,
    sr.price                                       as credits,
    nullif(sr.error_type, '')                      as error_type,
    'https://gooey.ai/' || wn.slug || '/?run_id=' || sr.run_id || '&uid=' || sr.uid as url
from bots_savedrun sr
left join workflow_names wn on wn.workflow = sr.workflow
left join surface_names sn on sn.surface = sr.surface
left join app_users_appuser u on u.uid = sr.uid
left join workspaces_workspace w on w.id = sr.workspace_id
where sr.run_id is not null
    [[and {{created_at}}]]
    [[and {{surface}}]]
    -- exclude team + anonymous users; drop these two lines to see everyone
    and coalesce(u.is_anonymous, false) = false
    and coalesce(u.email, '') not like '%@gooey.ai'
order by sr.created_at desc
limit 200
