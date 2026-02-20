# Buzzer Beater Tournament Dashboard

Single-file dashboard for team/player eligibility review with photo/docs preview and review tagging.

## Import Support

The upload section in `Tournament_Manager_Dashboard.html` accepts:

- `Registro Buzzer Beater - School (x_school)` (`.csv`, `.xlsx`, `.xls`)
- `School (x_school)` (`.csv`, `.xlsx`, `.xls`)

Parser behavior:

- Handles child-row style exports (teams + players nested in repeated rows).
- Supports both waiver column variants:
  - `x_studio_teams/x_studio_players/x_waiver_html`
  - `x_studio_teams/x_studio_players/x_studio_waiver_html`
- Detects CSV delimiters (comma or semicolon).
- If an import has no player rows, current working data is preserved (no overwrite).
- Last successful import is persisted in browser localStorage and restored on reload.

## Run Locally

Open `Tournament_Manager_Dashboard.html` directly in a browser, or serve it with a static server.

## Deploy (Netlify)

1. Push this repository to GitHub.
2. In Netlify, choose `Add new site` -> `Import an existing project`.
3. Select this repo.
4. Build settings:
   - Build command: *(leave empty)*
   - Publish directory: `.`
5. Deploy and share the generated URL.
6. Optional: attach a custom domain in `Domain settings`.

## Files

- `Tournament_Manager_Dashboard.html`: dashboard app (UI + parsing + review workflow)
- `create.py`: generator/transformation script used during data preparation
- CSV exports used for validation:
  - `Registro Buzzer Beater - School (x_school) (9).csv`
  - `School (x_school).csv`
