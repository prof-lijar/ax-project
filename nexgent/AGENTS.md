# Nexgent Project Instructions

These instructions apply to the entire `nexgent/` project unless a more
specific `AGENTS.md` file provides additional guidance for a subdirectory.

## Implementation Documentation

For every material implementation or infrastructure change:

1. Create or update an implementation document under `docs/` before handing
   off the work.
2. Give a new document a self-explanatory, topic-specific kebab-case filename.
   A reader must be able to understand the document's purpose from the filename
   alone. Prefer names such as `docker-development-stack.md`; do not use vague
   names such as `notes.md`, `changes.md`, or `update.md`.
3. Put `Date: YYYY-MM-DD` near the top of the document. Use the current date in
   the project timezone, Asia/Seoul. Do not silently replace dates on historical
   implementation records; add a clearly dated update when appropriate.
4. Add new documents to the document map in `docs/README.md` using a concise
   description of their scope.
5. Record what was implemented, important architecture or configuration
   decisions, run or operational commands, validation performed, known
   limitations, and any remaining verification or follow-up work.
6. Keep documentation claims aligned with actual validation. If an end-to-end
   check could not be run, state the reason and provide the exact remaining
   verification command.
