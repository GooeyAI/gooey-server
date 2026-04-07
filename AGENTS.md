## Code Style

- Prefer putting the main or public function above helper functions when editing files.
- When extracting helpers from a main or public function, keep the main/public function first and place the new helper below it.
- In migration files, keep the primary migration entrypoint or main backfill function first, with helper functions below it.
- In `RunPython` migrations, always use `db_alias = schema_editor.connection.alias` and run ORM operations through `.using(db_alias)`.
- Prefer simple data-driven mappings over layered helper abstractions when the data set is small and fixed.
- When building `selectbox` or `multiselect` options, prefer pre-rendered mappings like `options = {key: rendered_label}` and `format_func=options.__getitem__`.
- In Django admin, prefer shared link helpers like `list_related_html_url` for related-object changelist links instead of hand-building admin URLs.
- Prefer explicit early-return guards like `if not value: return` over wrapping the main body in conditionals when control flow allows it.
- Always use the virtual environment referenced by `.venv` for Python commands in this repo.
- `.venv` may be either a virtualenv directory or a text file containing the virtualenv name.
- If `.venv` is a file, resolve the env before running Python tools. In this repo, for example, `cat .venv` returns the virtualenv name and the interpreter may live at a path like `/Users/<user>/.virtualenvs/$(cat .venv)/bin/python`.
- Prefer invoking the env's executables directly, for example `/Users/<user>/.virtualenvs/$(cat .venv)/bin/python`, `/Users/<user>/.virtualenvs/$(cat .venv)/bin/pytest`, and `/Users/<user>/.virtualenvs/$(cat .venv)/bin/ruff`.
- Run `ruff` after making code edits and fix any reported issues before finishing.
- Do not push commits or update remote branches without explicit user confirmation.

## Gooey GUI Components

- `gooey-gui/app/components` supports dynamically rendered custom components from the Python render tree.
- For a component to participate in this system, the React component name, the file name, and the render-tree node name must match exactly. Example: `ComposioAuthRequired` lives in `gooey-gui/app/components/ComposioAuthRequired.tsx` and is rendered from Python with `gui.component("ComposioAuthRequired", ...)` or an equivalent wrapper.
- In `gooey-gui/app/components`, define these components with a named export in the form `export function <Name>({ ... }) { ... }`. Do not use `export default` for components that are meant to be resolved dynamically through `app/components/index.ts`.
- After adding a new dynamically rendered component under `gooey-gui/app/components`, add `export * from "./<Name>";` to `gooey-gui/app/components/index.ts`.
- These dynamically rendered components are cross-layer contracts. If you change the React component name or props, update the matching Python `gui.component(...)` call at the same time. If you change the Python render call name or props, update the matching React component signature and usage in the same change.
- The dynamic renderer passes the shared contract `props + children + onChange + state` to these components. Components that need render-tree children or form state should accept those props directly instead of relying on a special-case branch in `gooey-gui/app/renderer.tsx`.
- When nesting Python-rendered UI inside a dynamic component, prefer `with gui.component("Name", ...)` as a context manager on the Python side and render the passed child tree on the React side with `RenderedChildren` from `gooey-gui/app/renderer.tsx`. Do not render raw `children` directly in React; in this system they are render-tree nodes, not normal React children.
- Prefer moving app-specific custom components onto the dynamic component path instead of adding more one-off `case` branches to `gooey-gui/app/renderer.tsx`. Keep only true renderer primitives and special protocol nodes in the explicit switch.

## New Pages

- If you are asked to create a new page, create a React component for that page, add the corresponding Python route/page entrypoint, and render that React component from the new Python route.
- When the page should live inside the standard Gooey page shell, render the component under `page_wrapper` as appropriate instead of building a separate ad hoc layout path.
