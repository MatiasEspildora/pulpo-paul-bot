# PR helper: Add Country/LeagueId changes

This file is a tiny commit added to ensure the branch `feat/add-country-to-historico` has an explicit change to compare with `main` and create a pull request.

What this commit contains:
- A short note explaining the purpose of the branch and the change that was applied to `drivers/football.py` (add Country and LeagueId fields, use them in matching/deduplication).

After merging the PR, run the manual backfill according to the repo instructions to regenerate the `historico_mensual/football` CSVs and fill the new columns.

Suggested PR title:
`feat(football): add Country and LeagueId to historico_mensual; use them for matching/dedup`

Suggested PR body:
- Adds `Country` and `LeagueId` to historical records.
- Uses `LeagueId` first when matching/updating existing rows, falls back to `Country + League`, then `League`.
- Ensures CSVs missing the new columns are handled by the loader and reprocessed when running the backfill.

Once this PR is created, please run the "Manual backfill" workflow (Actions -> Manual backfill -> Run workflow) on the branch to regenerate CSVs.
