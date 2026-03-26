## Code Style

- Prefer putting the main or public function above helper functions when editing files.
- In migration files, keep the primary migration entrypoint or main backfill function first, with helper functions below it.
- In `RunPython` migrations, always use `db_alias = schema_editor.connection.alias` and run ORM operations through `.using(db_alias)`.
- Prefer simple data-driven mappings over layered helper abstractions when the data set is small and fixed.
- When building `selectbox` or `multiselect` options, prefer pre-rendered mappings like `options = {key: rendered_label}` and `format_func=options.__getitem__`.
- Run `ruff` after making code edits and fix any reported issues before finishing.
- Do not push commits or update remote branches without explicit user confirmation.
