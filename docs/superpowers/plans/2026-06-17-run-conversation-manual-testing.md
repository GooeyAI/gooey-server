# Manual Testing — VideoBots Conversation Grouping

Checkpoints for verifying the `RunConversation` feature end-to-end. The automated
suite (`pytest tests/test_run_conversation.py`, 11 tests) covers the model, stamping,
listers and payload shape; this doc covers the **runtime / UI behaviors** that can't
be exercised headlessly — especially the two regressions that were fixed (builder
streaming and the new-conversation leak).

## Setup / preconditions

- [ ] `manage.py migrate` applied cleanly (incl. `0123` workflow-drift, `0124` RunConversation).
- [ ] `manage.py makemigrations --check` → "No changes detected".
- [ ] Logged in as a **non-anonymous** user that has a workspace.
- [ ] `GOOEY_BUILDER_INTEGRATION_ID` configured (required for builder sections C–F).
- [ ] Start from an empty/known state for the test user (or note existing history).

---

## A. Playground — History tab shows one row per conversation

- [ ] Open VideoBots (Agent) playground. Start a **fresh** chat (no prior messages).
- [ ] Send message 1, then message 2, then message 3 in the **same** chat thread.
- [ ] Open the **History** tab → **exactly ONE** entry for that thread (not 3).
- [ ] The entry's title is the first prompt; the preview shows the **latest** turn.
- [ ] Click the entry → it resumes at the **latest** run (not the first).
- [ ] Click **New conversation** (resets `messages`) and send one message.
- [ ] History now shows a **NEW** entry, and it does **NOT** contain the previous 3 messages.

## A2. Copilot preview widget — conversation list grouped

> The agent page's embedded chat widget lists past chats via
> `/__/agent/fetch-conversations`, now grouped one row per conversation.

- [ ] In the VideoBots playground, open the embedded copilot widget's conversation list.
- [ ] Each past chat is **one row per conversation** (not one per turn), newest first.
- [ ] Clicking a conversation opens its latest run (resume).
- [ ] (Forward-only) Conversations whose runs predate this feature won't appear until backfilled.

## B. Builder — response streams (regression: Bug 1)

- [ ] Open the builder sidebar on a VideoBots page. Send a message.
- [ ] The assistant reply **streams token-by-token** (you see partial text grow),
      **not** just the final answer appearing all at once.
- [ ] After it finishes, the final response renders normally (buttons/links intact).

## C. Builder — new conversation does not leak (regression: Bug 2)

- [ ] Have an existing builder conversation with ≥2 turns.
- [ ] Click **New conversation** in the builder, then send a message.
- [ ] The new conversation shows **only** the new exchange — **none** of the previous
      conversation's messages appear.
- [ ] Send a 2nd message in this new conversation → it stays in the **same** (new)
      conversation (does not spawn yet another conversation per message).

## D. Builder — sidebar lists one row per conversation

- [ ] Open the builder conversations list (sidebar).
- [ ] Each conversation is **one row** (not one row per turn).
- [ ] Newest-active conversation is at the top; title matches its first prompt.
- [ ] Clicking a conversation opens its **latest** run (resume).

## E. Admin

- [ ] `/admin/bots/runconversation/` lists conversations: title, Workflow (label, e.g.
      "Agent"), Surface (Run/Builder), **Messages**, Last Run, uid, timestamps.
- [ ] Click the **Messages** link on a row → opens the **SavedRun changelist filtered to
      that conversation**, showing all runs that belong to it (count matches).
- [ ] Open any SavedRun detail page → the **Conversation** field links back to its
      `RunConversation`.
- [ ] `list_filter` (workflow / surface / created_at) and search (id / title / uid) work.

## F. Per-message URL payload (for the upcoming widget change)

> The widget doesn't render these links yet (separate gooey-web-widget follow-up); this
> just confirms the server emits the data.

- [ ] In the builder, inspect the `GooeyBuilderInlineEmbed` props (React devtools) or the
      render payload → a **`conversation_messages`** prop is present.
- [ ] Each assistant entry in it carries **`saved_run_url`** and **`builder_run_url`**.
- [ ] `messages` (the live display) is still produced separately — streaming (section B)
      is unaffected by the presence of `conversation_messages`.

## G. Regression — other workflows unaffected

- [ ] Open a **non-VideoBots** workflow (e.g. Compare LLM). Its History tab still lists
      individual runs as before (`supports_conversations = False`).
- [ ] No `RunConversation` rows are created for non-VideoBots runs.

## H. Data integrity spot-checks (optional, via shell/admin)

- [ ] For a multi-turn conversation, all its runs share one `conversation_id`
      (`SavedRun.conversation`), and `RunConversation.last_run` points to the newest turn.
- [ ] A "New conversation" produces a distinct `RunConversation` row (different id).
