import re
from html import unescape
from urllib.parse import parse_qs, urlparse

import pandas as pd

file_path = "Registro Buzzer Beater - School (x_school) (9).csv"
df = pd.read_csv(file_path)

# 1. Forward fill team and school information downwards
cols_to_ffill = [
    'Nombre del Colegio', 
    'x_studio_teams/x_name', 
    'x_studio_teams/x_studio_sex', 
    'x_studio_teams/x_studio_category'
]
df[cols_to_ffill] = df[cols_to_ffill].ffill()

# 2. Filter rows that actually have a player (ignores extra staff rows)
df_players = df.dropna(subset=['x_studio_teams/x_studio_players/x_name']).copy()

# 3. Extract and normalize Google Drive links from HTML cells
HREF_RE = re.compile(r'href=[\'"]?([^\'" >]+)', re.IGNORECASE)
IMG_SRC_RE = re.compile(r'<img[^>]*src=[\'"]([^\'"]+)[\'"]', re.IGNORECASE)
DRIVE_ID_PATH_RE = re.compile(r"/file/d/([A-Za-z0-9_-]+)")
GENERIC_DRIVE_D_RE = re.compile(r"/d/([A-Za-z0-9_-]+)")


def extract_href(html_string):
    if pd.isna(html_string):
        return ""
    match = HREF_RE.search(str(html_string))
    if not match:
        return ""
    return unescape(match.group(1)).strip()


def extract_drive_file_id(url):
    if not url:
        return ""
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower()
    if "drive.google.com" not in host and "docs.google.com" not in host:
        return ""

    path_match = DRIVE_ID_PATH_RE.search(parsed.path)
    if path_match:
        return path_match.group(1)

    d_match = GENERIC_DRIVE_D_RE.search(parsed.path)
    if d_match:
        return d_match.group(1)

    query = parse_qs(parsed.query)
    if query.get("id"):
        return query["id"][0]
    return ""


def canonical_drive_view_url(url):
    file_id = extract_drive_file_id(url)
    if not file_id:
        return url
    return f"https://drive.google.com/file/d/{file_id}/view?usp=drive_link"


def drive_preview_url(url):
    file_id = extract_drive_file_id(url)
    if not file_id:
        return ""
    return f"https://drive.google.com/file/d/{file_id}/preview"


def drive_thumbnail_url(url):
    file_id = extract_drive_file_id(url)
    if not file_id:
        return ""
    return f"https://drive.google.com/thumbnail?id={file_id}&sz=w400"


def extract_url(html_string):
    href = extract_href(html_string)
    if not href:
        return ""
    return canonical_drive_view_url(href)


# 4. Extract a reliable image URL for player thumbnails
def extract_photo_url(html_string):
    if pd.isna(html_string):
        return ""

    html_text = str(html_string)
    img_match = IMG_SRC_RE.search(html_text)
    if img_match:
        img_url = unescape(img_match.group(1)).strip()
        # Drive thumbnail URLs render more consistently than raw uc links.
        thumb = drive_thumbnail_url(img_url)
        if thumb:
            return thumb
        return img_url

    href = extract_href(html_text)
    if href:
        thumb = drive_thumbnail_url(href)
        if thumb:
            return thumb
    return ""


def extract_photo_full_url(html_string):
    """Best-effort full image URL for modal view (without thumbnail downsizing)."""
    if pd.isna(html_string):
        return ""
    img_match = IMG_SRC_RE.search(str(html_string))
    if not img_match:
        return ""
    return unescape(img_match.group(1)).strip()

df_players['Birth Certificate'] = df_players['x_studio_teams/x_studio_players/x_studio_certificado_de_nacimiento_html'].apply(extract_url)
df_players['Waiver'] = df_players['x_studio_teams/x_studio_players/x_waiver_html'].apply(extract_url)
df_players['Birth Certificate Preview'] = df_players['Birth Certificate'].apply(drive_preview_url)
df_players['Waiver Preview'] = df_players['Waiver'].apply(drive_preview_url)

# Extract photos from BOTH birth cert and waiver columns (some have photos in cert, some in waiver)
df_players['Photo_from_cert'] = df_players['x_studio_teams/x_studio_players/x_studio_certificado_de_nacimiento_html'].apply(extract_photo_url)
df_players['Photo_from_waiver'] = df_players['x_studio_teams/x_studio_players/x_waiver_html'].apply(extract_photo_url)
df_players['Photo_full_from_cert'] = df_players['x_studio_teams/x_studio_players/x_studio_certificado_de_nacimiento_html'].apply(extract_photo_full_url)
df_players['Photo_full_from_waiver'] = df_players['x_studio_teams/x_studio_players/x_waiver_html'].apply(extract_photo_full_url)

# Use cert photo; fall back to waiver photo if cert has none
def pick_photo(row):
    if row['Photo_from_cert']:
        return row['Photo_from_cert']
    return row['Photo_from_waiver']


def pick_photo_full(row):
    if row['Photo_full_from_cert']:
        return row['Photo_full_from_cert']
    return row['Photo_full_from_waiver']

df_players['Photo'] = df_players.apply(pick_photo, axis=1)
df_players['Photo Full'] = df_players.apply(pick_photo_full, axis=1)

# 5. Clean up columns and rename them for the dashboard
dashboard_df = df_players[[
    'Nombre del Colegio', 'x_studio_teams/x_name', 'x_studio_teams/x_studio_sex',
    'x_studio_teams/x_studio_category', 'x_studio_teams/x_studio_players/x_name',
    'x_studio_teams/x_studio_players/x_studio_date_of_birth',
    'x_studio_teams/x_studio_players/x_studio_jersey_number',
    'x_studio_teams/x_studio_players/x_studio_grade',
    'Birth Certificate', 'Waiver', 'Birth Certificate Preview', 'Waiver Preview', 'Photo', 'Photo Full'
]].copy()

dashboard_df.columns = [
    'School', 'Team', 'Gender', 'Category', 
    'Player Name', 'Date of Birth', 'Jersey #', 'Grade',
    'Birth Certificate', 'Waiver', 'Birth Certificate Preview', 'Waiver Preview', 'Photo', 'Photo Full'
]

# 6. Format the Date of Birth nicely
dashboard_df['DOB_display'] = pd.to_datetime(dashboard_df['Date of Birth'], errors='coerce').dt.strftime('%B %d, %Y')
dashboard_df['DOB_display'] = dashboard_df['DOB_display'].fillna(dashboard_df['Date of Birth'])

# 7. Build the data structure for the template
teams_data = {}
player_counter = 1
for _, row in dashboard_df.iterrows():
    team_key = row['Team']
    if team_key not in teams_data:
        teams_data[team_key] = {
            'team': row['Team'],
            'school': row['School'],
            'gender': row['Gender'],
            'category': row['Category'],
            'players': []
        }
    teams_data[team_key]['players'].append({
        'record_id': f"player_{player_counter:04d}",
        'name': row['Player Name'],
        'dob': row['Date of Birth'],
        'dob_display': row['DOB_display'],
        'jersey': str(int(row['Jersey #'])) if pd.notna(row['Jersey #']) else '—',
        'grade': row['Grade'],
        'cert_url': row['Birth Certificate'],
        'waiver_url': row['Waiver'],
        'cert_preview': row['Birth Certificate Preview'],
        'waiver_preview': row['Waiver Preview'],
        'photo': row['Photo'],
        'photo_full': row['Photo Full'],
    })
    player_counter += 1

# 8. Build player rows for the table view (all players flat)
def make_link(url, label="View", button_class="btn btn-sm btn-outline-primary"):
    if url:
        return (
            f'<a href="{url}" target="_blank" rel="noopener noreferrer" '
            f'class="{button_class}">{label}</a>'
        )
    return '<span class="text-muted small">—</span>'

# Convert teams_data to JSON-safe structure for JavaScript embedding
import json

teams_json = []
for source_idx, (team_key, team_info) in enumerate(teams_data.items()):
    players_list = []
    for p in team_info['players']:
        players_list.append({
            'record_id': p['record_id'],
            'name': p['name'],
            'dob': p['dob'],
            'dob_display': p['dob_display'],
            'jersey': p['jersey'],
            'grade': p['grade'],
            'cert_url': p['cert_url'],
            'waiver_url': p['waiver_url'],
            'cert_preview': p['cert_preview'],
            'waiver_preview': p['waiver_preview'],
            'photo': p['photo'],
            'photo_full': p['photo_full'],
        })
    teams_json.append({
        'source_idx': source_idx,
        'team': team_info['team'],
        'school': team_info['school'],
        'gender': team_info['gender'],
        'category': team_info['category'],
        'players': players_list,
    })

teams_json_str = json.dumps(teams_json, ensure_ascii=False, indent=2)

# Generate the table rows for the data table
table_rows = ""
for _, row in dashboard_df.iterrows():
    photo_html = ""
    if row['Photo']:
        photo_html = f'<img src="{row["Photo"]}" alt="{row["Player Name"]}" class="mini-photo" onerror="this.style.display=\'none\'">'
    else:
        photo_html = '<div class="no-photo-mini">📷</div>'
    
    cert_link = make_link(row['Birth Certificate'], '📋 Open')
    cert_preview_link = make_link(
        row['Birth Certificate Preview'],
        '🔎 Preview',
        'btn btn-sm btn-outline-warning'
    )
    waiver_link = make_link(row['Waiver'], '✍️ Open')
    
    table_rows += f"""
        <tr>
            <td class="photo-cell">{photo_html}</td>
            <td class="player-name-cell">
                <span class="player-name">{row['Player Name']}</span>
                <span class="jersey-badge">#{row['Jersey #'] if pd.notna(row['Jersey #']) else '—'}</span>
            </td>
            <td class="dob-cell">
                <span class="dob-badge">{row['DOB_display']}</span>
            </td>
            <td class="doc-cell">{cert_link} {cert_preview_link}</td>
            <td class="doc-cell">{waiver_link}</td>
            <td class="school-cell">{row['School']}</td>
            <td class="team-cell"><span class="gender-tag {'male-tag' if row['Gender'] == 'Masculino' else 'female-tag'}">{row['Gender'][:1]}</span> {row['Team']}</td>
            <td>{row['Grade']}</td>
            <td><span class="category-tag">{row['Category']}</span></td>
        </tr>"""

html_template = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🏀 Buzzer Beater — Tournament Dashboard</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {{
            --primary: #f97316;
            --primary-dark: #ea580c;
            --primary-light: #fed7aa;
            --secondary: #1e293b;
            --accent: #0ea5e9;
            --accent2: #8b5cf6;
            --bg: #0f172a;
            --surface: #1e293b;
            --surface2: #334155;
            --border: #334155;
            --text: #f1f5f9;
            --text-muted: #94a3b8;
            --male: #38bdf8;
            --female: #f472b6;
            --success: #22c55e;
            --radius: 14px;
        }}

        * {{ box-sizing: border-box; margin: 0; padding: 0; }}

        body {{
            background: var(--bg);
            color: var(--text);
            font-family: 'Inter', sans-serif;
            min-height: 100vh;
            overflow-x: hidden;
        }}

        /* Background grid */
        body::before {{
            content: '';
            position: fixed;
            inset: 0;
            background-image:
                linear-gradient(rgba(249,115,22,0.03) 1px, transparent 1px),
                linear-gradient(90deg, rgba(249,115,22,0.03) 1px, transparent 1px);
            background-size: 40px 40px;
            pointer-events: none;
            z-index: 0;
        }}

        /* ── HEADER ── */
        .hero {{
            position: relative;
            z-index: 1;
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #0c1a2e 100%);
            border-bottom: 1px solid var(--border);
            padding: 28px 40px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 16px;
        }}
        .hero::after {{
            content: '';
            position: absolute;
            bottom: -1px;
            left: 0;
            right: 0;
            height: 2px;
            background: linear-gradient(90deg, transparent, var(--primary), var(--accent), transparent);
        }}
        .hero-brand {{
            display: flex;
            align-items: center;
            gap: 16px;
        }}
        .hero-icon {{
            width: 56px; height: 56px;
            background: linear-gradient(135deg, var(--primary), var(--primary-dark));
            border-radius: 14px;
            display: flex; align-items: center; justify-content: center;
            font-size: 28px;
            box-shadow: 0 8px 24px rgba(249,115,22,0.35);
        }}
        .hero-title {{ font-size: 1.8rem; font-weight: 800; line-height: 1.1; }}
        .hero-title span {{ color: var(--primary); }}
        .hero-sub {{ color: var(--text-muted); font-size: 0.85rem; margin-top: 2px; }}

        .hero-stats {{
            display: flex; gap: 24px; flex-wrap: wrap;
        }}
        .stat-pill {{
            background: rgba(255,255,255,0.05);
            border: 1px solid var(--border);
            border-radius: 999px;
            padding: 8px 18px;
            display: flex; align-items: center; gap: 8px;
            font-size: 0.85rem; font-weight: 500;
        }}
        .stat-pill .num {{ font-weight: 700; font-size: 1.1rem; color: var(--primary); }}

        /* ── TABS ── */
        .main-tabs {{
            position: relative; z-index: 1;
            display: flex;
            background: var(--surface);
            border-bottom: 1px solid var(--border);
            padding: 0 40px;
        }}
        .tab-btn {{
            background: none; border: none; color: var(--text-muted);
            padding: 16px 24px;
            font-family: 'Inter', sans-serif;
            font-size: 0.9rem; font-weight: 500;
            cursor: pointer;
            border-bottom: 2px solid transparent;
            transition: all 0.2s;
            display: flex; align-items: center; gap: 8px;
        }}
        .tab-btn:hover {{ color: var(--text); }}
        .tab-btn.active {{ color: var(--primary); border-bottom-color: var(--primary); }}
        .tab-count {{
            background: var(--surface2); border-radius: 999px;
            padding: 2px 8px; font-size: 0.75rem; font-weight: 600;
        }}
        .tab-btn.active .tab-count {{
            background: rgba(249,115,22,0.2); color: var(--primary);
        }}

        /* ── TOOLBAR ── */
        .toolbar {{
            position: relative; z-index: 1;
            padding: 20px 40px;
            display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
        }}
        .search-box {{
            flex: 1; min-width: 240px; max-width: 420px;
            position: relative;
        }}
        .search-box input {{
            width: 100%;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 10px;
            color: var(--text);
            padding: 10px 16px 10px 40px;
            font-family: 'Inter', sans-serif;
            font-size: 0.9rem;
            outline: none;
            transition: border-color 0.2s;
        }}
        .search-box input:focus {{ border-color: var(--primary); }}
        .search-box input::placeholder {{ color: var(--text-muted); }}
        .search-icon {{
            position: absolute; left: 13px; top: 50%; transform: translateY(-50%);
            font-size: 16px; pointer-events: none;
        }}
        .filter-btn {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 10px;
            color: var(--text-muted);
            padding: 10px 16px;
            font-family: 'Inter', sans-serif; font-size: 0.85rem; font-weight: 500;
            cursor: pointer; transition: all 0.2s;
        }}
        .filter-btn:hover, .filter-btn.active {{ border-color: var(--primary); color: var(--primary); }}
        .filter-btn.gender-m.active {{ border-color: var(--male); color: var(--male); }}
        .filter-btn.gender-f.active {{ border-color: var(--female); color: var(--female); }}

        /* ── CONTENT ── */
        .content-area {{
            position: relative; z-index: 1;
            padding: 0 40px 40px;
        }}

        .tab-panel {{ display: none; }}
        .tab-panel.active {{ display: block; }}

        /* ── TEAM CARDS GRID ── */
        .teams-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
            gap: 24px;
            padding-top: 8px;
        }}

        .team-card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: var(--radius);
            overflow: hidden;
            transition: transform 0.2s, box-shadow 0.2s, border-color 0.2s;
        }}
        .team-card:hover {{
            transform: translateY(-3px);
            box-shadow: 0 16px 40px rgba(0,0,0,0.4);
            border-color: var(--primary);
        }}

        .team-header {{
            padding: 18px 20px 14px;
            display: flex; justify-content: space-between; align-items: flex-start;
            background: linear-gradient(135deg, rgba(249,115,22,0.08), rgba(14,165,233,0.04));
            border-bottom: 1px solid var(--border);
        }}
        .team-name-block {{ flex: 1; }}
        .team-name {{
            font-size: 1rem; font-weight: 700; line-height: 1.2;
            margin-bottom: 4px;
        }}
        .team-meta {{ display: flex; gap: 6px; flex-wrap: wrap; margin-top: 6px; }}

        .badge-pill {{
            padding: 3px 10px; border-radius: 999px; font-size: 0.72rem; font-weight: 600;
        }}
        .badge-cat-Publica   {{ background: rgba(34,197,94,0.15); color: #4ade80; }}
        .badge-cat-Senior    {{ background: rgba(249,115,22,0.15); color: var(--primary); }}
        .badge-cat-Junior    {{ background: rgba(139,92,246,0.15); color: #a78bfa; }}
        .badge-cat-Juvenil   {{ background: rgba(14,165,233,0.15); color: var(--accent); }}
        .badge-cat-Mini      {{ background: rgba(244,114,182,0.15); color: #f472b6; }}
        .badge-cat-default   {{ background: rgba(100,116,139,0.15); color: var(--text-muted); }}

        .badge-gender {{
            padding: 3px 10px; border-radius: 999px; font-size: 0.72rem; font-weight: 700;
        }}
        .badge-m {{ background: rgba(56,189,248,0.15); color: var(--male); }}
        .badge-f {{ background: rgba(244,114,182,0.15); color: var(--female); }}

        .player-count {{
            background: var(--surface2); border-radius: 10px;
            padding: 6px 12px; text-align: center;
            font-size: 0.75rem; color: var(--text-muted); min-width: 52px;
        }}
        .player-count .num {{ font-size: 1.3rem; font-weight: 800; color: var(--text); display: block; }}

        /* ── PHOTO GRID ── */
        .players-photo-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(80px, 1fr));
            gap: 8px;
            padding: 16px;
        }}

        .player-tile {{
            position: relative;
            cursor: pointer;
        }}
        .player-tile img, .player-tile .no-photo {{
            width: 100%;
            aspect-ratio: 3/4;
            object-fit: cover;
            border-radius: 10px;
            border: 2px solid transparent;
            transition: border-color 0.2s, transform 0.2s;
            display: block;
        }}
        .no-photo {{
            background: var(--surface2);
            display: flex; align-items: center; justify-content: center;
            font-size: 24px;
            border: 2px solid var(--border);
            border-radius: 10px;
            aspect-ratio: 3/4;
        }}
        .player-tile:hover img, .player-tile:hover .no-photo {{
            border-color: var(--primary);
            transform: scale(1.04);
        }}
        .jersey-num {{
            position: absolute; top: 4px; left: 4px;
            background: rgba(15,23,42,0.85);
            color: var(--text);
            font-size: 0.65rem; font-weight: 800;
            padding: 2px 5px; border-radius: 5px;
            backdrop-filter: blur(4px);
        }}
        .player-review-flag {{
            position: absolute; bottom: 4px; right: 4px;
            font-size: 0.62rem; font-weight: 700;
            border-radius: 999px; padding: 2px 6px;
            border: 1px solid transparent;
            background: rgba(15,23,42,0.85);
            color: var(--text-muted);
        }}
        .player-review-flag.review {{
            background: rgba(249,115,22,0.18);
            color: var(--primary);
            border-color: rgba(249,115,22,0.4);
        }}
        .player-review-flag.correct-review {{
            background: rgba(34,197,94,0.18);
            color: #86efac;
            border-color: rgba(34,197,94,0.4);
        }}

        /* ── DOB HOVER TOOLTIP ── */
        .player-tile .dob-tooltip {{
            position: absolute;
            bottom: calc(100% + 8px);
            left: 50%;
            transform: translateX(-50%);
            background: rgba(15,23,42,0.97);
            border: 1px solid var(--primary);
            border-radius: 10px;
            padding: 10px 14px;
            min-width: 170px;
            pointer-events: none;
            opacity: 0;
            transition: opacity 0.18s;
            z-index: 1000;
            backdrop-filter: blur(12px);
            box-shadow: 0 8px 32px rgba(0,0,0,0.5), 0 0 0 1px rgba(249,115,22,0.2);
            text-align: center;
        }}
        .player-tile:hover .dob-tooltip {{ opacity: 1; }}
        .player-tile .dob-tooltip::after {{
            content: '';
            position: absolute;
            top: 100%;
            left: 50%;
            transform: translateX(-50%);
            border: 6px solid transparent;
            border-top-color: var(--primary);
        }}
        .tooltip-name {{ font-size: 0.78rem; font-weight: 600; color: var(--text); margin-bottom: 6px; }}
        .tooltip-label {{ font-size: 0.65rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 2px; }}
        .tooltip-dob {{ font-size: 0.88rem; font-weight: 700; color: var(--primary); }}
        .tooltip-jersey {{ font-size: 0.7rem; color: var(--text-muted); margin-top: 4px; }}
        .tooltip-grade {{ font-size: 0.7rem; color: var(--accent); margin-top: 2px; }}
        .tooltip-docs {{ margin-top: 8px; display: flex; gap: 6px; justify-content: center; flex-wrap: wrap; }}
        .tooltip-link {{
            font-size: 0.7rem; font-weight: 600;
            padding: 3px 8px; border-radius: 6px;
            text-decoration: none;
            background: rgba(249,115,22,0.12);
            color: var(--primary);
            border: 1px solid rgba(249,115,22,0.25);
            pointer-events: all;
            transition: background 0.15s;
        }}
        .tooltip-link:hover {{ background: rgba(249,115,22,0.25); }}
        .tooltip-link.waiver {{
            background: rgba(14,165,233,0.12);
            color: var(--accent);
            border-color: rgba(14,165,233,0.25);
        }}
        .tooltip-link.waiver:hover {{ background: rgba(14,165,233,0.25); }}

        /* ── TABLE VIEW ── */
        .table-wrapper {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: var(--radius);
            overflow: hidden;
            margin-top: 8px;
        }}
        .table {{ color: var(--text) !important; margin: 0 !important; }}
        .table thead th {{
            background: linear-gradient(135deg, rgba(249,115,22,0.1), rgba(14,165,233,0.05)) !important;
            color: var(--text-muted) !important;
            border-bottom: 1px solid var(--border) !important;
            font-size: 0.75rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em;
            padding: 14px 12px !important;
            white-space: nowrap;
        }}
        .table tbody tr {{
            border-bottom: 1px solid rgba(51,65,85,0.5) !important;
            transition: background 0.15s;
        }}
        .table tbody tr:hover {{ background: rgba(249,115,22,0.04) !important; }}
        .table tbody td {{
            padding: 10px 12px !important;
            border: none !important;
            vertical-align: middle;
            color: var(--text) !important;
        }}
        .mini-photo {{
            width: 38px; height: 48px;
            object-fit: cover;
            border-radius: 7px;
            border: 2px solid var(--border);
        }}
        .no-photo-mini {{
            width: 38px; height: 48px;
            background: var(--surface2);
            border-radius: 7px;
            display: flex; align-items: center; justify-content: center;
            font-size: 16px;
            border: 2px solid var(--border);
        }}
        .player-name {{ font-weight: 600; font-size: 0.9rem; }}
        .jersey-badge {{
            display: inline-block;
            background: rgba(249,115,22,0.12); color: var(--primary);
            border-radius: 5px; padding: 1px 6px;
            font-size: 0.72rem; font-weight: 700;
            margin-left: 6px;
        }}
        .dob-badge {{
            font-family: monospace; font-size: 0.85rem; font-weight: 600;
            color: var(--accent);
        }}
        .gender-tag {{
            display: inline-flex; align-items: center; justify-content: center;
            width: 20px; height: 20px; border-radius: 999px;
            font-size: 0.65rem; font-weight: 800;
        }}
        .male-tag {{ background: rgba(56,189,248,0.2); color: var(--male); }}
        .female-tag {{ background: rgba(244,114,182,0.2); color: var(--female); }}
        .category-tag {{
            padding: 2px 8px; border-radius: 6px;
            font-size: 0.72rem; font-weight: 600;
            background: var(--surface2); color: var(--text-muted);
        }}

        /* DataTables overrides */
        .dataTables_wrapper .dataTables_length select,
        .dataTables_wrapper .dataTables_filter input {{
            background: var(--surface2) !important;
            border: 1px solid var(--border) !important;
            color: var(--text) !important;
            border-radius: 8px !important;
            padding: 6px 12px !important;
            font-family: 'Inter', sans-serif;
        }}
        .dataTables_wrapper .dataTables_length label,
        .dataTables_wrapper .dataTables_filter label,
        .dataTables_wrapper .dataTables_info {{
            color: var(--text-muted) !important;
            font-size: 0.85rem;
        }}
        .dataTables_wrapper .dataTables_paginate .paginate_button {{
            color: var(--text-muted) !important;
            border-radius: 8px !important;
        }}
        .dataTables_wrapper .dataTables_paginate .paginate_button.current {{
            background: var(--primary) !important;
            border-color: var(--primary) !important;
            color: white !important;
        }}
        .dataTables_wrapper .dataTables_paginate .paginate_button:hover {{
            background: var(--surface2) !important;
            border-color: var(--border) !important;
            color: var(--text) !important;
        }}
        .btn-outline-primary {{
            border-color: var(--primary) !important;
            color: var(--primary) !important;
            font-size: 0.72rem !important;
            padding: 3px 8px !important;
        }}
        .btn-outline-primary:hover {{
            background: var(--primary) !important;
            color: white !important;
        }}
        .doc-cell {{ white-space: nowrap; }}
        .school-cell {{ font-size: 0.82rem; color: var(--text-muted); }}
        .team-cell {{ font-size: 0.8rem; }}

        /* ── REVIEW BOARD ── */
        .review-toolbar {{
            margin: 8px 0 12px;
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            align-items: center;
        }}
        .review-search {{
            min-width: 260px;
            max-width: 540px;
            flex: 1 1 340px;
        }}
        .review-summary {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-bottom: 12px;
        }}
        .review-pill {{
            background: rgba(255,255,255,0.05);
            border: 1px solid var(--border);
            border-radius: 999px;
            padding: 6px 12px;
            font-size: 0.78rem;
            color: var(--text-muted);
        }}
        .review-pill strong {{
            color: var(--text);
            margin-left: 6px;
        }}
        .review-table tbody td {{
            font-size: 0.82rem;
            vertical-align: top;
        }}
        .review-note-cell {{
            max-width: 320px;
            white-space: pre-wrap;
            line-height: 1.35;
            color: var(--text);
        }}
        .review-updated-cell {{
            white-space: nowrap;
            font-family: monospace;
            color: var(--text-muted);
            font-size: 0.76rem;
        }}
        .review-status-badge {{
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            padding: 2px 10px;
            font-size: 0.72rem;
            font-weight: 700;
            border: 1px solid transparent;
        }}
        .review-status-badge.none {{
            color: var(--text-muted);
            border-color: var(--border);
            background: rgba(148,163,184,0.08);
        }}
        .review-status-badge.review {{
            color: var(--primary);
            border-color: rgba(249,115,22,0.35);
            background: rgba(249,115,22,0.15);
        }}
        .review-status-badge.correct-review {{
            color: #86efac;
            border-color: rgba(34,197,94,0.4);
            background: rgba(34,197,94,0.16);
        }}
        .review-open-btn {{
            border: 1px solid rgba(14,165,233,0.35);
            background: rgba(14,165,233,0.14);
            color: var(--accent);
            border-radius: 8px;
            padding: 4px 10px;
            font-size: 0.74rem;
            font-weight: 700;
            cursor: pointer;
        }}
        .review-open-btn:hover {{
            background: rgba(14,165,233,0.25);
        }}

        /* ── SCHOOL SIDEBAR ── */
        .school-filter-list {{
            display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 4px;
        }}
        .school-tag {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 6px 12px;
            font-size: 0.8rem; font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
            color: var(--text-muted);
        }}
        .school-tag.active {{ border-color: var(--primary); color: var(--primary); background: rgba(249,115,22,0.07); }}
        .school-tag:hover {{ border-color: var(--primary); color: var(--text); }}

        /* ── MODAL ── */
        .player-modal-overlay {{
            display: none;
            position: fixed; inset: 0; z-index: 2000;
            background: rgba(0,0,0,0.75);
            backdrop-filter: blur(6px);
            align-items: center; justify-content: center;
        }}
        .player-modal-overlay.open {{ display: flex; }}
        .player-modal {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 20px;
            width: min(760px, 96vw);
            max-height: 96vh;
            overflow-y: auto;
            box-shadow: 0 32px 80px rgba(0,0,0,0.6);
            animation: modalIn 0.25s ease;
        }}
        @keyframes modalIn {{
            from {{ opacity: 0; transform: scale(0.94) translateY(10px); }}
            to   {{ opacity: 1; transform: scale(1) translateY(0); }}
        }}
        .modal-photo {{
            width: 100%;
            max-height: min(70vh, 760px);
            object-fit: contain;
            background: #020617;
            border-radius: 20px 20px 0 0;
        }}
        .modal-media {{
            position: relative;
        }}
        .modal-photo-tags {{
            position: absolute;
            top: 10px;
            left: 10px;
            right: 52px;
            display: flex;
            gap: 6px;
            flex-wrap: wrap;
            align-items: center;
            pointer-events: none;
            z-index: 5;
        }}
        .modal-photo-tags .modal-tag-btn {{
            pointer-events: auto;
            background: rgba(15,23,42,0.76);
            backdrop-filter: blur(4px);
        }}
        .modal-no-photo {{
            height: min(56vh, 520px);
            background: linear-gradient(135deg, rgba(249,115,22,0.1), rgba(14,165,233,0.05));
            display: flex; align-items: center; justify-content: center;
            font-size: 64px; border-radius: 20px 20px 0 0;
        }}
        .modal-body-inner {{ padding: 14px 16px 16px; }}
        .modal-headline {{
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 10px;
            margin-bottom: 10px;
        }}
        .modal-name {{ font-size: 1.08rem; font-weight: 800; margin-bottom: 3px; line-height: 1.15; }}
        .modal-team {{ color: var(--text-muted); font-size: 0.76rem; }}
        .modal-nav {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 8px;
            margin-bottom: 10px;
        }}
        .modal-nav-meta {{
            font-size: 0.72rem;
            color: var(--text-muted);
            font-weight: 600;
        }}
        .modal-nav-btn {{
            background: var(--surface2);
            border: 1px solid var(--border);
            color: var(--text);
            border-radius: 8px;
            padding: 5px 9px;
            font-size: 0.72rem;
            font-weight: 700;
            cursor: pointer;
        }}
        .modal-nav-btn:hover {{ border-color: var(--primary); color: var(--primary); }}
        .modal-nav-btn:disabled {{
            opacity: 0.45;
            cursor: not-allowed;
            border-color: var(--border);
            color: var(--text-muted);
        }}
        .modal-quick-info {{
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            margin-bottom: 10px;
        }}
        .modal-chip {{
            border-radius: 999px;
            border: 1px solid var(--border);
            background: rgba(148,163,184,0.12);
            color: var(--text);
            font-size: 0.72rem;
            font-weight: 700;
            padding: 4px 10px;
            line-height: 1.2;
        }}
        .modal-chip.dob {{
            border-color: rgba(249,115,22,0.34);
            background: rgba(249,115,22,0.16);
            color: var(--primary);
        }}
        .modal-chip.grade {{
            border-color: rgba(14,165,233,0.34);
            background: rgba(14,165,233,0.16);
            color: var(--accent);
        }}
        .modal-chip.status-review {{
            border-color: rgba(249,115,22,0.35);
            background: rgba(249,115,22,0.16);
            color: var(--primary);
        }}
        .modal-chip.status-correct-review {{
            border-color: rgba(34,197,94,0.4);
            background: rgba(34,197,94,0.16);
            color: #86efac;
        }}
        .modal-docs {{
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            margin-bottom: 10px;
        }}
        .modal-doc-btn {{
            text-align: center;
            background: rgba(249,115,22,0.12);
            border: 1px solid rgba(249,115,22,0.25);
            color: var(--primary); border-radius: 10px;
            padding: 7px 10px; text-decoration: none;
            font-weight: 700; font-size: 0.74rem;
            transition: background 0.15s;
        }}
        .modal-doc-btn:hover {{ background: rgba(249,115,22,0.22); color: var(--primary); }}
        .modal-doc-btn.waiver {{
            background: rgba(14,165,233,0.12);
            border-color: rgba(14,165,233,0.25);
            color: var(--accent);
        }}
        .modal-doc-btn.waiver:hover {{ background: rgba(14,165,233,0.22); }}
        .modal-review-box {{
            border: 1px solid var(--border);
            border-radius: 12px;
            background: rgba(148,163,184,0.06);
            padding: 10px;
        }}
        .modal-review-title {{
            font-size: 0.66rem;
            text-transform: uppercase;
            letter-spacing: 0.07em;
            color: var(--text-muted);
            margin-bottom: 7px;
        }}
        .modal-tag-btn {{
            background: var(--surface2);
            border: 1px solid var(--border);
            color: var(--text);
            border-radius: 999px;
            padding: 5px 10px;
            font-size: 0.72rem;
            font-weight: 700;
            cursor: pointer;
            line-height: 1.2;
        }}
        .modal-tag-btn:hover {{
            border-color: var(--primary);
            color: var(--primary);
        }}
        .modal-tag-btn.active {{
            border-color: var(--text-muted);
            color: var(--text);
            background: rgba(148,163,184,0.16);
        }}
        .modal-tag-btn.active.review {{
            border-color: rgba(249,115,22,0.4);
            background: rgba(249,115,22,0.18);
            color: var(--primary);
        }}
        .modal-tag-btn.active.correct-review {{
            border-color: rgba(34,197,94,0.44);
            background: rgba(34,197,94,0.2);
            color: #86efac;
        }}
        .modal-review-row-wrap.hidden {{
            display: none;
        }}
        .modal-review-row {{
            display: grid;
            grid-template-columns: 1fr auto;
            gap: 8px;
            align-items: end;
        }}
        .modal-review-note {{
            width: 100%;
            min-height: 56px;
            resize: vertical;
            background: var(--surface2);
            border: 1px solid var(--border);
            border-radius: 8px;
            color: var(--text);
            padding: 8px 10px;
            font-size: 0.76rem;
            line-height: 1.3;
            font-family: inherit;
        }}
        .modal-review-save {{
            background: rgba(34,197,94,0.16);
            border: 1px solid rgba(34,197,94,0.38);
            color: #86efac;
            border-radius: 8px;
            height: 36px;
            padding: 0 12px;
            font-size: 0.74rem;
            font-weight: 700;
            cursor: pointer;
        }}
        .modal-review-save:hover {{
            background: rgba(34,197,94,0.25);
        }}
        .modal-review-meta {{
            margin-top: 6px;
            font-size: 0.7rem;
            color: var(--text-muted);
        }}
        .modal-close {{
            position: absolute; top: 16px; right: 16px;
            width: 32px; height: 32px;
            background: rgba(0,0,0,0.5); border: none; border-radius: 50%;
            color: white; font-size: 18px; cursor: pointer;
            display: flex; align-items: center; justify-content: center;
            transition: background 0.15s;
        }}
        .modal-close:hover {{ background: rgba(249,115,22,0.5); }}
        .modal-inner-wrap {{ position: relative; }}

        /* ── EMPTY STATE ── */
        .empty-state {{
            text-align: center; padding: 60px 20px; color: var(--text-muted);
        }}
        .empty-state .icon {{ font-size: 48px; margin-bottom: 12px; }}

        /* ── RESPONSIVE ── */
        @media (max-width: 700px) {{
            .hero {{ padding: 20px; }}
            .content-area, .toolbar, .main-tabs {{ padding-left: 16px; padding-right: 16px; }}
            .teams-grid {{ grid-template-columns: 1fr; }}
            .modal-review-row {{ grid-template-columns: 1fr; }}
            .modal-review-save {{ width: 100%; }}
        }}
    </style>
</head>
<body>

<!-- ══ HEADER ══ -->
<div class="hero">
    <div class="hero-brand">
        <div class="hero-icon">🏀</div>
        <div>
            <div class="hero-title">Buzzer Beater <span>Tournament</span></div>
            <div class="hero-sub">Player Eligibility &amp; Documents Dashboard</div>
        </div>
    </div>
    <div class="hero-stats" id="heroStats"></div>
</div>

<!-- ══ TABS ══ -->
<div class="main-tabs">
    <button class="tab-btn active" onclick="switchTab('teams', this)">
        🏟️ Teams &amp; Players
        <span class="tab-count" id="teamsCount">—</span>
    </button>
    <button class="tab-btn" onclick="switchTab('review', this)">
        📝 Review Board
        <span class="tab-count" id="reviewCount">—</span>
    </button>
</div>

<!-- ══ TEAMS FILTERS ══ -->
<div id="teamsFilters">
    <div class="toolbar">
        <div class="search-box">
            <span class="search-icon">🔍</span>
            <input type="text" id="mainSearch" placeholder="Search player, school, team…" oninput="applyFilters()">
        </div>
        <button class="filter-btn gender-m" id="filterM" onclick="toggleGender('Masculino')">♂ Masculino</button>
        <button class="filter-btn gender-f" id="filterF" onclick="toggleGender('Femenino')">♀ Femenino</button>
        <button class="filter-btn" id="filterAll" onclick="clearFilters()" style="display:none">✕ Clear</button>
    </div>

    <div style="padding: 0 40px 16px; position:relative; z-index:1;" id="schoolTagArea">
        <div class="school-filter-list" id="schoolTags"></div>
    </div>
</div>

<!-- ══ CONTENT ══ -->
<div class="content-area">
    <!-- TEAMS PANEL -->
    <div class="tab-panel active" id="panel-teams">
        <div class="teams-grid" id="teamsGrid"></div>
        <div class="empty-state" id="noTeams" style="display:none">
            <div class="icon">🔍</div>
            <div>No teams match your search.</div>
        </div>
    </div>

    <!-- REVIEW PANEL -->
    <div class="tab-panel" id="panel-review">
        <div class="review-toolbar">
            <div class="search-box review-search">
                <span class="search-icon">🗂️</span>
                <input type="text" id="reviewSearch" placeholder="Search player, team, school, or note…" oninput="renderReviewBoard()">
            </div>
            <button class="filter-btn review-filter active" onclick="setReviewFilter('all', this)">All</button>
            <button class="filter-btn review-filter" onclick="setReviewFilter('review', this)">Review</button>
            <button class="filter-btn review-filter" onclick="setReviewFilter('correct_review', this)">Correct Review</button>
            <button class="filter-btn review-filter" onclick="setReviewFilter('flagged', this)">Tagged</button>
        </div>

        <div class="review-summary" id="reviewSummary"></div>

        <div class="table-wrapper">
            <table class="table review-table">
                <thead>
                    <tr>
                        <th>Player</th>
                        <th>DOB</th>
                        <th>School</th>
                        <th>Team</th>
                        <th>Status</th>
                        <th>Note</th>
                        <th>Updated</th>
                        <th>Open</th>
                    </tr>
                </thead>
                <tbody id="reviewRows"></tbody>
            </table>
        </div>

        <div class="empty-state" id="noReviewRows" style="display:none">
            <div class="icon">📝</div>
            <div>No review records match this filter.</div>
        </div>
    </div>
</div>

<!-- ══ PLAYER MODAL ══ -->
<div class="player-modal-overlay" id="playerModal" onclick="closeModal(event)">
    <div class="player-modal">
        <div class="modal-inner-wrap">
            <button class="modal-close" onclick="document.getElementById('playerModal').classList.remove('open')">✕</button>
            <div id="modalContent"></div>
        </div>
    </div>
</div>

<!-- Scripts -->
<script>
const TEAMS_DATA = {teams_json_str};

// ── INIT ──
const TEAM_BY_SOURCE_IDX = {{}};
TEAMS_DATA.forEach(team => {{
    TEAM_BY_SOURCE_IDX[team.source_idx] = team;
}});

const ALL_PLAYERS = [];
TEAMS_DATA.forEach(team => {{
    team.players.forEach((p, playerIdx) => {{
        ALL_PLAYERS.push({{
            record_id: p.record_id,
            name: p.name,
            dob: p.dob,
            dob_display: p.dob_display,
            school: team.school,
            team: team.team,
            category: team.category,
            gender: team.gender,
            team_source_idx: team.source_idx,
            player_idx: playerIdx,
        }});
    }});
}});

const REVIEW_STORAGE_KEY = 'bb_review_state_v1';
let reviewState = loadReviewState();
let genderFilter = null;
let schoolFilter = null;
let activeTab = 'teams';
let reviewFilter = 'all';

let visibleRecords = [];
let reviewRecords = [];
let modalSequence = [];
let modalSequencePos = -1;
let currentPlayerRef = null;

window.addEventListener('DOMContentLoaded', () => {{
    buildSchoolTags();
    applyFilters();
    renderReviewBoard();
    updateHeroStats();
}});

function loadReviewState() {{
    try {{
        const raw = localStorage.getItem(REVIEW_STORAGE_KEY);
        if (!raw) return {{}};
        const parsed = JSON.parse(raw);
        return parsed && typeof parsed === 'object' ? parsed : {{}};
    }} catch (err) {{
        return {{}};
    }}
}}

function persistReviewState() {{
    localStorage.setItem(REVIEW_STORAGE_KEY, JSON.stringify(reviewState));
}}

function getPlayerKey(player) {{
    return player && player.record_id ? player.record_id : '';
}}

function getReviewEntry(player) {{
    const key = getPlayerKey(player);
    if (!key || !reviewState[key]) {{
        return {{ status: '', note: '', updated_at: '' }};
    }}
    return {{
        status: reviewState[key].status || '',
        note: reviewState[key].note || '',
        updated_at: reviewState[key].updated_at || '',
    }};
}}

function setReviewEntry(player, status, note) {{
    const key = getPlayerKey(player);
    if (!key) return;
    const cleanStatus = status || '';
    const cleanNote = (note || '').trim();

    if (!cleanStatus && !cleanNote) {{
        delete reviewState[key];
    }} else {{
        reviewState[key] = {{
            status: cleanStatus,
            note: cleanNote,
            updated_at: new Date().toISOString(),
        }};
    }}
    persistReviewState();
}}

function statusLabel(status) {{
    if (status === 'review') return 'Review';
    if (status === 'correct_review') return 'Correct Review';
    return 'No Tag';
}}

function statusShort(status) {{
    if (status === 'review') return 'Review';
    if (status === 'correct_review') return 'Correct';
    return '';
}}

function statusClass(status) {{
    if (status === 'review') return 'review';
    if (status === 'correct_review') return 'correct-review';
    return 'none';
}}

function formatUpdated(ts) {{
    if (!ts) return '—';
    const d = new Date(ts);
    if (Number.isNaN(d.getTime())) return ts;
    return d.toLocaleString();
}}

function updateHeroStats() {{
    const totalTeams = TEAMS_DATA.length;
    const totalPlayers = TEAMS_DATA.reduce((s, t) => s + t.players.length, 0);
    const schools = [...new Set(TEAMS_DATA.map(t => t.school))].length;
    const withPhotos = TEAMS_DATA.reduce((s, t) => s + t.players.filter(p => p.photo).length, 0);
    const withCert = TEAMS_DATA.reduce((s, t) => s + t.players.filter(p => p.cert_url).length, 0);
    const tagged = Object.values(reviewState).filter(v => (v.status || '').length > 0).length;
    const reviewOnly = Object.values(reviewState).filter(v => v.status === 'review').length;
    const correctOnly = Object.values(reviewState).filter(v => v.status === 'correct_review').length;

    document.getElementById('heroStats').innerHTML = `
        <div class="stat-pill"><span class="num">${{totalTeams}}</span> Teams</div>
        <div class="stat-pill"><span class="num">${{totalPlayers}}</span> Players</div>
        <div class="stat-pill"><span class="num">${{schools}}</span> Schools</div>
        <div class="stat-pill"><span class="num">${{withCert}}</span> 📋 Cert Links</div>
        <div class="stat-pill"><span class="num">${{withPhotos}}</span> 📷 Photos</div>
        <div class="stat-pill"><span class="num">${{tagged}}</span> 🏷️ Tagged</div>
        <div class="stat-pill"><span class="num">${{reviewOnly}}</span> ⚠️ Review</div>
        <div class="stat-pill"><span class="num">${{correctOnly}}</span> ✅ Correct</div>
    `;
    document.getElementById('teamsCount').textContent = totalTeams;
    document.getElementById('reviewCount').textContent = tagged;
}}

// ── SCHOOL TAGS ──
function buildSchoolTags() {{
    const schools = [...new Set(TEAMS_DATA.map(t => t.school))].sort();
    const container = document.getElementById('schoolTags');
    container.innerHTML = '';
    schools.forEach(school => {{
        const tag = document.createElement('button');
        tag.className = 'school-tag';
        tag.textContent = school;
        tag.onclick = () => toggleSchool(school, tag);
        container.appendChild(tag);
    }});
}}

function toggleSchool(school, el) {{
    if (schoolFilter === school) {{
        schoolFilter = null;
        document.querySelectorAll('.school-tag').forEach(t => t.classList.remove('active'));
    }} else {{
        schoolFilter = school;
        document.querySelectorAll('.school-tag').forEach(t => {{
            t.classList.toggle('active', t.textContent === school);
        }});
    }}
    applyFilters();
}}

// ── GENDER FILTER ──
function toggleGender(g) {{
    if (genderFilter === g) {{
        genderFilter = null;
    }} else {{
        genderFilter = g;
    }}
    document.getElementById('filterM').classList.toggle('active', genderFilter === 'Masculino');
    document.getElementById('filterF').classList.toggle('active', genderFilter === 'Femenino');
    document.getElementById('filterAll').style.display = genderFilter ? 'block' : 'none';
    applyFilters();
}}

function clearFilters() {{
    genderFilter = null;
    schoolFilter = null;
    document.getElementById('mainSearch').value = '';
    document.getElementById('filterM').classList.remove('active');
    document.getElementById('filterF').classList.remove('active');
    document.getElementById('filterAll').style.display = 'none';
    document.querySelectorAll('.school-tag').forEach(t => t.classList.remove('active'));
    applyFilters();
}}

function getFilteredTeams() {{
    const q = document.getElementById('mainSearch').value.toLowerCase();
    return TEAMS_DATA.filter(team => {{
        if (genderFilter && team.gender !== genderFilter) return false;
        if (schoolFilter && team.school !== schoolFilter) return false;
        if (q) {{
            const searchable = (team.team + ' ' + team.school + ' ' + team.players.map(p => p.name).join(' ')).toLowerCase();
            if (!searchable.includes(q)) return false;
        }}
        return true;
    }});
}}

// ── APPLY FILTERS ──
function applyFilters() {{
    renderTeamsGrid(getFilteredTeams());
}}

function switchTab(tab, btn) {{
    activeTab = tab;
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('panel-' + tab).classList.add('active');
    document.getElementById('teamsFilters').style.display = tab === 'teams' ? 'block' : 'none';
    if (tab === 'review') {{
        renderReviewBoard();
    }}
}}

function setReviewFilter(filter, btn) {{
    reviewFilter = filter;
    document.querySelectorAll('.review-filter').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    renderReviewBoard();
}}

function openModalByVisiblePos(pos) {{
    openRecordFromSequence(visibleRecords, pos);
}}

function openModalByReviewPos(pos) {{
    openRecordFromSequence(reviewRecords, pos);
}}

function openRecordFromSequence(sequence, pos) {{
    if (!sequence || sequence.length === 0 || pos < 0 || pos >= sequence.length) {{
        return;
    }}

    modalSequence = sequence.map(item => ({{
        team_source_idx: item.team_source_idx,
        player_idx: item.player_idx,
    }}));
    modalSequencePos = pos;

    const ref = modalSequence[pos];
    const team = TEAM_BY_SOURCE_IDX[ref.team_source_idx];
    if (!team || !team.players || !team.players[ref.player_idx]) {{
        return;
    }}

    currentPlayerRef = ref;
    openModal(team.players[ref.player_idx], team.team);
}}

function goPrevRecord() {{
    if (modalSequencePos <= 0) return;
    openRecordFromSequence(modalSequence, modalSequencePos - 1);
}}

function goNextRecord() {{
    if (modalSequencePos < 0 || modalSequencePos >= modalSequence.length - 1) return;
    openRecordFromSequence(modalSequence, modalSequencePos + 1);
}}

function handleImgErr(img) {{
    if (!img) return;
    img.outerHTML = '<div class="no-photo">🏀</div>';
}}

function handleModalImgErr(img) {{
    if (!img) return;
    const fallback = img.dataset.fallback || '';
    const fallbackUsed = img.dataset.fallbackUsed === '1';
    if (!fallbackUsed && fallback && img.src !== fallback) {{
        img.dataset.fallbackUsed = '1';
        img.src = fallback;
        return;
    }}
    img.outerHTML = '<div class="modal-no-photo">🏀</div>';
}}

// ── RENDER TEAMS GRID ──
function renderTeamsGrid(teams) {{
    const grid = document.getElementById('teamsGrid');
    const empty = document.getElementById('noTeams');
    visibleRecords = [];

    if (teams.length === 0) {{
        grid.innerHTML = '';
        empty.style.display = 'block';
        return;
    }}
    empty.style.display = 'none';

    grid.innerHTML = teams.map((team) => {{
        const catClass = 'badge-cat-' + (team.category || 'default');
        const gClass = team.gender === 'Masculino' ? 'badge-m' : 'badge-f';
        const gSymbol = team.gender === 'Masculino' ? '♂' : '♀';

        const playerTiles = team.players.map((p, pi) => {{
            const visiblePos = visibleRecords.push({{
                team_source_idx: team.source_idx,
                player_idx: pi,
            }}) - 1;
            const review = getReviewEntry(p);
            const reviewClass = statusClass(review.status);
            const reviewFlag = review.status
                ? `<div class="player-review-flag ${{reviewClass}}">${{statusShort(review.status)}}</div>`
                : '';
            const photoHtml = p.photo
                ? `<img src="${{p.photo}}" alt="${{p.name}}" loading="lazy" onerror="handleImgErr(this)">`
                : `<div class="no-photo">🏀</div>`;

            const certLink = p.cert_url ? `<a href="${{p.cert_url}}" target="_blank" class="tooltip-link" onclick="event.stopPropagation()">📋 Cert</a>` : '';
            const waiverLink = p.waiver_url ? `<a href="${{p.waiver_url}}" target="_blank" class="tooltip-link waiver" onclick="event.stopPropagation()">✍️ Waiver</a>` : '';
            const reviewText = review.status ? `<div class="tooltip-grade">${{statusLabel(review.status)}}</div>` : '';

            return `
            <div class="player-tile" onclick="openModalByVisiblePos(${{visiblePos}})">
                ${{photoHtml}}
                <div class="jersey-num">#${{p.jersey}}</div>
                ${{reviewFlag}}
                <div class="dob-tooltip">
                    <div class="tooltip-name">${{p.name}}</div>
                    <div class="tooltip-label">Date of Birth</div>
                    <div class="tooltip-jersey">Jersey #${{p.jersey}}</div>
                    <div class="tooltip-grade">Grade: ${{p.grade}}</div>
                    ${{reviewText}}
                    <div class="tooltip-docs">${{certLink}} ${{waiverLink}}</div>
                </div>
            </div>`;
        }}).join('');

        return `
        <div class="team-card">
            <div class="team-header">
                <div class="team-name-block">
                    <div class="team-name">${{team.team}}</div>
                    <div class="team-meta">
                        <span class="badge-pill badge-cat-${{team.category || 'default'}}">${{team.category}}</span>
                        <span class="badge-gender ${{gClass}}">${{gSymbol}} ${{team.gender}}</span>
                    </div>
                </div>
                <div class="player-count">
                    <span class="num">${{team.players.length}}</span>
                    Players
                </div>
            </div>
            <div class="players-photo-grid">${{playerTiles}}</div>
        </div>`;
    }}).join('');
}}

function renderReviewBoard() {{
    const q = document.getElementById('reviewSearch').value.toLowerCase().trim();

    let rows = ALL_PLAYERS.map(base => {{
        const entry = reviewState[base.record_id] || {{}};
        return {{
            ...base,
            status: entry.status || '',
            note: entry.note || '',
            updated_at: entry.updated_at || '',
        }};
    }});

    if (reviewFilter === 'review') {{
        rows = rows.filter(r => r.status === 'review');
    }} else if (reviewFilter === 'correct_review') {{
        rows = rows.filter(r => r.status === 'correct_review');
    }} else if (reviewFilter === 'flagged') {{
        rows = rows.filter(r => !!r.status);
    }}

    if (q) {{
        rows = rows.filter(r => {{
            const bag = (r.name + ' ' + r.school + ' ' + r.team + ' ' + r.note + ' ' + statusLabel(r.status)).toLowerCase();
            return bag.includes(q);
        }});
    }}

    const rank = {{ review: 0, correct_review: 1, '': 2 }};
    rows.sort((a, b) => {{
        const rd = (rank[a.status || ''] ?? 99) - (rank[b.status || ''] ?? 99);
        if (rd !== 0) return rd;
        const sd = a.school.localeCompare(b.school);
        if (sd !== 0) return sd;
        const td = a.team.localeCompare(b.team);
        if (td !== 0) return td;
        return a.name.localeCompare(b.name);
    }});

    reviewRecords = rows.map(r => ({{
        team_source_idx: r.team_source_idx,
        player_idx: r.player_idx,
    }}));

    const totalTagged = Object.values(reviewState).filter(v => (v.status || '').length > 0).length;
    const totalReview = Object.values(reviewState).filter(v => v.status === 'review').length;
    const totalCorrect = Object.values(reviewState).filter(v => v.status === 'correct_review').length;
    document.getElementById('reviewSummary').innerHTML = `
        <div class="review-pill">Players <strong>${{ALL_PLAYERS.length}}</strong></div>
        <div class="review-pill">Tagged <strong>${{totalTagged}}</strong></div>
        <div class="review-pill">Review <strong>${{totalReview}}</strong></div>
        <div class="review-pill">Correct Review <strong>${{totalCorrect}}</strong></div>
        <div class="review-pill">Visible Rows <strong>${{rows.length}}</strong></div>
    `;

    const tbody = document.getElementById('reviewRows');
    const empty = document.getElementById('noReviewRows');
    if (rows.length === 0) {{
        tbody.innerHTML = '';
        empty.style.display = 'block';
        return;
    }}
    empty.style.display = 'none';

    tbody.innerHTML = rows.map((r, idx) => `
        <tr>
            <td><strong>${{escHtml(r.name)}}</strong></td>
            <td class="dob-cell"><span class="dob-badge">${{escHtml(r.dob_display || r.dob || '—')}}</span></td>
            <td class="school-cell">${{escHtml(r.school)}}</td>
            <td class="team-cell">${{escHtml(r.team)}}</td>
            <td><span class="review-status-badge ${{statusClass(r.status)}}">${{statusLabel(r.status)}}</span></td>
            <td class="review-note-cell">${{r.note ? escHtml(r.note) : '<span style="color:var(--text-muted)">—</span>'}}</td>
            <td class="review-updated-cell">${{formatUpdated(r.updated_at)}}</td>
            <td><button class="review-open-btn" onclick="openModalByReviewPos(${{idx}})">Open</button></td>
        </tr>
    `).join('');
}}

// ── MODAL ──
function openModal(playerData, teamName) {{
    const p = typeof playerData === 'string' ? JSON.parse(playerData) : playerData;
    const review = getReviewEntry(p);
    const totalInSequence = modalSequence.length || 1;
    const displayPos = modalSequencePos >= 0 ? modalSequencePos + 1 : 1;
    const team = currentPlayerRef ? TEAM_BY_SOURCE_IDX[currentPlayerRef.team_source_idx] : null;
    const teamLine = team && team.school ? `${{teamName}} | ${{team.school}}` : teamName;
    const modalPhoto = p.photo_full || p.photo;

    const photoHtml = modalPhoto
        ? `<img src="${{modalPhoto}}" data-fallback="${{p.photo || ''}}" data-fallback-used="0" alt="${{p.name}}" class="modal-photo" onerror="handleModalImgErr(this)">`
        : `<div class="modal-no-photo">🏀</div>`;

    const certBtn = p.cert_url ? `<a href="${{p.cert_url}}" target="_blank" class="modal-doc-btn">📋 Birth Certificate</a>` : '';
    const certPreviewBtn = p.cert_preview ? `<a href="${{p.cert_preview}}" target="_blank" class="modal-doc-btn">🔎 Preview Certificate</a>` : '';
    const waiverBtn = p.waiver_url ? `<a href="${{p.waiver_url}}" target="_blank" class="modal-doc-btn waiver">✍️ Waiver</a>` : '';
    const waiverPreviewBtn = p.waiver_preview ? `<a href="${{p.waiver_preview}}" target="_blank" class="modal-doc-btn waiver">🔎 Preview Waiver</a>` : '';
    const reviewMeta = review.updated_at ? `Last saved: ${{formatUpdated(review.updated_at)}}` : 'No review saved yet.';
    const statusChipClass = review.status ? `status-${{statusClass(review.status)}}` : '';
    const statusChip = review.status
        ? `<span class="modal-chip ${{statusChipClass}}">${{statusLabel(review.status)}}</span>`
        : '';

    document.getElementById('modalContent').innerHTML = `
        <div class="modal-media">
            ${{photoHtml}}
            <div class="modal-photo-tags">
                <input type="hidden" id="modalReviewStatus" value="">
                <button class="modal-tag-btn review" id="tagBtnReview" onclick="setModalStatus('review', true)">⚠️ Review</button>
                <button class="modal-tag-btn correct-review" id="tagBtnCorrect" onclick="setModalStatus('correct_review', true)">✅ Correct Review</button>
                <button class="modal-tag-btn" id="tagBtnClear" onclick="setModalStatus('', true)">Clear</button>
            </div>
        </div>
        <div class="modal-body-inner">
            <div class="modal-nav">
                <button class="modal-nav-btn" onclick="goPrevRecord()" ${{modalSequencePos <= 0 ? 'disabled' : ''}}>← Previous</button>
                <div class="modal-nav-meta">Record ${{displayPos}} of ${{totalInSequence}}</div>
                <button class="modal-nav-btn" onclick="goNextRecord()" ${{modalSequencePos >= totalInSequence - 1 ? 'disabled' : ''}}>Next →</button>
            </div>
            <div class="modal-headline">
                <div>
                    <div class="modal-name">${{escHtml(p.name)}}</div>
                    <div class="modal-team">${{escHtml(teamLine)}}</div>
                </div>
            </div>
            <div class="modal-quick-info">
                <span class="modal-chip dob">DOB: ${{escHtml(p.dob_display || p.dob || '—')}}</span>
                <span class="modal-chip">Jersey #${{escHtml(p.jersey || '—')}}</span>
                <span class="modal-chip grade">Grade: ${{escHtml(p.grade || '—')}}</span>
                ${{statusChip}}
            </div>
            <div class="modal-docs">${{certBtn}} ${{certPreviewBtn}} ${{waiverBtn}} ${{waiverPreviewBtn}}</div>
            <div class="modal-review-box">
                <div class="modal-review-title">Review Note</div>
                <div id="modalReviewRowWrap" class="modal-review-row-wrap">
                <div class="modal-review-row">
                    <textarea id="modalReviewNote" class="modal-review-note" placeholder="Add note (optional)"></textarea>
                    <button class="modal-review-save" onclick="saveCurrentReview()">Save Note</button>
                </div>
                </div>
                <div class="modal-review-meta" id="modalReviewMeta">${{reviewMeta}}</div>
            </div>
        </div>
    `;
    document.getElementById('modalReviewStatus').value = review.status || '';
    document.getElementById('modalReviewNote').value = review.note || '';
    updateModalTagButtons(review.status || '');
    updateReviewNoteVisibility(review.status || '');
    document.getElementById('playerModal').classList.add('open');
}}

function updateModalTagButtons(status) {{
    const reviewBtn = document.getElementById('tagBtnReview');
    const correctBtn = document.getElementById('tagBtnCorrect');
    const clearBtn = document.getElementById('tagBtnClear');
    if (!reviewBtn || !correctBtn || !clearBtn) return;

    reviewBtn.classList.toggle('active', status === 'review');
    correctBtn.classList.toggle('active', status === 'correct_review');
    clearBtn.classList.toggle('active', !status);
}}

function setModalStatus(status, autoSave = false) {{
    const statusEl = document.getElementById('modalReviewStatus');
    if (!statusEl) return;
    statusEl.value = status || '';
    updateModalTagButtons(statusEl.value);
    updateReviewNoteVisibility(statusEl.value);
    if (autoSave) {{
        saveCurrentReview();
    }}
}}

function updateReviewNoteVisibility(status) {{
    const wrap = document.getElementById('modalReviewRowWrap');
    const noteEl = document.getElementById('modalReviewNote');
    const metaEl = document.getElementById('modalReviewMeta');
    if (!wrap || !noteEl || !metaEl) return;

    const showNote = status === 'review';
    wrap.classList.toggle('hidden', !showNote);
    noteEl.disabled = !showNote;
    noteEl.placeholder = showNote ? 'Add note (required for review)' : '';

    if (!showNote) {{
        noteEl.value = '';
        if (metaEl.textContent.trim() === '' || metaEl.textContent.includes('No review saved yet.')) {{
            metaEl.textContent = 'Notes are only available when status is Review.';
        }}
    }}
}}

function saveCurrentReview() {{
    if (!currentPlayerRef) return;
    const team = TEAM_BY_SOURCE_IDX[currentPlayerRef.team_source_idx];
    if (!team || !team.players || !team.players[currentPlayerRef.player_idx]) return;
    const player = team.players[currentPlayerRef.player_idx];

    const statusEl = document.getElementById('modalReviewStatus');
    const noteEl = document.getElementById('modalReviewNote');
    if (!statusEl || !noteEl) return;

    const status = statusEl.value;
    const note = status === 'review' ? noteEl.value : '';
    setReviewEntry(player, status, note);

    const updated = getReviewEntry(player);
    const meta = updated.updated_at ? `Last saved: ${{formatUpdated(updated.updated_at)}}` : 'No review saved yet.';
    document.getElementById('modalReviewMeta').textContent = meta;
    updateModalTagButtons(updated.status || '');
    updateReviewNoteVisibility(updated.status || '');

    if (activeTab === 'teams') {{
        applyFilters();
    }}
    renderReviewBoard();
    updateHeroStats();
}}

function closeModal(e) {{
    if (e.target === document.getElementById('playerModal')) {{
        document.getElementById('playerModal').classList.remove('open');
    }}
}}

function escHtml(str) {{
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}}
</script>
</body>
</html>
"""

with open("Tournament_Manager_Dashboard.html", "w", encoding="utf-8") as f:
    f.write(html_template)

print("Dashboard generated.")
print(f"Teams: {len(teams_json)}")
print(f"Players: {sum(len(t['players']) for t in teams_json)}")
print(f"Players with photos: {sum(1 for t in teams_json for p in t['players'] if p['photo'])}")
