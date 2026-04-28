import io
import json
import os
import random
import re
import time
import unicodedata
from urllib.parse import urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup

# --- Configuration ---
CSV_FILE = "AI_soccer_urls.csv"
OUTPUT_JSON = "rosters_pos_stats.json"
SEASON = "2025"

# Batch controls for test runs.
# Use START_INDEX = 0 and BATCH_SIZE = 10 to scrape the first 10 teams in the CSV.
# Set BATCH_SIZE = None to process the full file.
START_INDEX = 0
BATCH_SIZE = 10

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

POSITION_BUCKETS = {
    "forwards": {"goals", "assists", "points", "shots", "gp", "gs"},
    "goalkeepers": {"saves", "ga", "gaa", "sho", "gp", "gs"},
}


def fetch_page(url):
    try:
        time.sleep(random.uniform(1.0, 2.0))
        response = SESSION.get(url, timeout=20)
        response.raise_for_status()
        return response.text
    except Exception:
        return None


def clean_text(value):
    if value is None:
        return ""
    text = str(value).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def safe_int(val):
    try:
        if pd.isna(val):
            return 0
        return int(float(val))
    except (ValueError, TypeError):
        return 0


def normalize_name(name):
    text = unicodedata.normalize("NFKD", clean_text(name))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^\w\s'-]", " ", text.lower())
    text = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def dedupe_repeated_text(text):
    text = clean_text(text)
    if not text:
        return text

    half = len(text) // 2
    if len(text) % 2 == 0 and text[:half].lower() == text[half:].lower():
        return text[:half]

    for token in ["Forward", "Midfielder", "Defender", "Goalkeeper"]:
        doubled = f"{token}{token.lower()[1:]}"
        if text.lower() == doubled.lower():
            return token

    return text


def seasonize_url(url, page_type):
    url = clean_text(url)
    if not url:
        return url

    parsed = urlparse(url)
    if parsed.netloc.endswith("sidearmsports.com"):
        return url

    path = parsed.path.rstrip("/")
    if re.search(rf"/{SEASON}$", path):
        return url

    if page_type == "stats" and re.search(r"/statistics?$", path, re.I):
        return f"{parsed.scheme}://{parsed.netloc}{path}/{SEASON}"

    if page_type == "stats" and re.search(r"/stats$", path, re.I):
        return f"{parsed.scheme}://{parsed.netloc}{path}/{SEASON}"

    if page_type == "roster" and re.search(r"/roster$", path, re.I):
        return f"{parsed.scheme}://{parsed.netloc}{path}/{SEASON}"

    return url


def extract_gp_gs(row):
    gp_gs_col = next((c for c in row.index if "gp" in c and "gs" in c), None)
    if gp_gs_col and pd.notna(row[gp_gs_col]):
        parts = [p for p in re.split(r"\D+", str(row[gp_gs_col]).strip()) if p]
        gp = safe_int(parts[0]) if len(parts) > 0 else 0
        gs = safe_int(parts[1]) if len(parts) > 1 else 0
        return gp, gs

    gp_col = next((c for c in row.index if c in ["gp", "games played"]), None)
    gs_col = next((c for c in row.index if c in ["gs", "games started"]), None)
    gp = safe_int(row[gp_col]) if gp_col else 0
    gs = safe_int(row[gs_col]) if gs_col else 0
    return gp, gs


def map_position(raw_pos_string):
    raw = dedupe_repeated_text(raw_pos_string)
    if not raw:
        return "midfielders"

    primary = re.split(r"[/,\-]", str(raw))[0].strip().upper()
    if primary.startswith("F") or primary == "STR" or "FORWARD" in primary:
        return "forwards"
    if primary.startswith("M"):
        return "midfielders"
    if primary.startswith("D") or primary.startswith("B") or "BACK" in primary:
        return "defenders"
    if primary.startswith("G"):
        return "goalkeepers"
    return "midfielders"


def get_single_text(tag):
    if not tag:
        return ""

    pieces = [clean_text(s) for s in tag.stripped_strings if clean_text(s)]
    if not pieces:
        return ""

    # Sidearm often renders nested spans that duplicate the visible label.
    unique = []
    seen = set()
    for piece in pieces:
        lowered = piece.lower()
        if lowered not in seen:
            seen.add(lowered)
            unique.append(piece)

    joined = " ".join(unique)
    return dedupe_repeated_text(joined)


def parse_roster_cards(soup):
    roster_dict = {"forwards": [], "midfielders": [], "defenders": [], "goalkeepers": []}
    seen_players = set()
    roster_cards = soup.find_all(class_=re.compile(r"sidearm-roster-player$"))

    for card in roster_cards:
        try:
            name_tag = card.find(class_="sidearm-roster-player-name")
            number_tag = card.find(class_="sidearm-roster-player-jersey-number")
            position_tag = card.find(class_="sidearm-roster-player-position")

            name = get_single_text(name_tag)
            number = get_single_text(number_tag)
            raw_pos = get_single_text(position_tag)

            if not name:
                continue

            player_key = (normalize_name(name), clean_text(number))
            if player_key in seen_players:
                continue
            seen_players.add(player_key)

            roster_dict[map_position(raw_pos)].append(
                {
                    "name": name,
                    "number": safe_int(number) if re.fullmatch(r"\d+", clean_text(number)) else number or "NA",
                    "listed_position": raw_pos or "Midfielder",
                }
            )
        except Exception:
            continue

    return roster_dict


def parse_roster_table(soup):
    roster_dict = {"forwards": [], "midfielders": [], "defenders": [], "goalkeepers": []}
    seen_players = set()

    for table in soup.find_all("table"):
        headers = [clean_text(th.get_text()).lower() for th in table.find_all("th")]
        if not headers:
            continue

        if not any("name" in h or "player" in h for h in headers):
            continue

        rows = table.find_all("tr")
        for row in rows[1:]:
            cells = [clean_text(td.get_text()) for td in row.find_all(["td", "th"])]
            if len(cells) < 2:
                continue

            row_text = " ".join(cells)
            if not re.search(r"[A-Za-z][A-Za-z' -]+ [A-Za-z][A-Za-z' -]+", row_text):
                continue

            number = "NA"
            name = ""
            raw_pos = ""

            for idx, header in enumerate(headers[: len(cells)]):
                value = cells[idx]
                if "name" in header or "player" in header:
                    name = value
                elif header in {"#", "no.", "num", "number"} or "jersey" in header:
                    number = value
                elif "pos" in header:
                    raw_pos = value

            if not name:
                if re.fullmatch(r"\d+", cells[0]):
                    number = cells[0]
                    name = cells[1]
                    raw_pos = cells[2] if len(cells) > 2 else ""
                else:
                    name = cells[0]
                    raw_pos = cells[1] if len(cells) > 1 else ""

            player_key = (normalize_name(name), clean_text(number))
            if player_key in seen_players:
                continue
            seen_players.add(player_key)

            roster_dict[map_position(raw_pos)].append(
                {
                    "name": name,
                    "number": safe_int(number) if re.fullmatch(r"\d+", clean_text(number)) else number or "NA",
                    "listed_position": dedupe_repeated_text(raw_pos) or "Midfielder",
                }
            )

    return roster_dict


def parse_roster(html):
    soup = BeautifulSoup(html, "html.parser")
    roster_dict = parse_roster_cards(soup)
    total_players = sum(len(players) for players in roster_dict.values())
    if total_players >= 11:
        return roster_dict
    return parse_roster_table(soup)


def normalize_columns(df):
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(-1)

    df.columns = [
        re.sub(r"\s+", " ", str(col).strip().lower()).replace("\n", " ") for col in df.columns
    ]
    df = df.loc[:, ~pd.Index(df.columns).duplicated()]

    rename_map = {
        "player": "player",
        "name": "player",
        "player name": "player",
        "gp-gs": "gp_gs",
        "gp gs": "gp_gs",
        "g-gs": "gp_gs",
        "shots": "sh",
        "shot": "sh",
        "points": "pts",
        "sv": "saves",
        "sogsv": "saves",
        "shutouts": "sho",
        "goals against": "ga",
        "goals-against": "ga",
    }
    df = df.rename(columns={col: rename_map.get(col, col) for col in df.columns})
    return df


def clean_stats_df(df):
    if df is None or df.empty:
        return None

    df = normalize_columns(df.copy())
    if "player" not in df.columns:
        return None

    df["player"] = df["player"].map(clean_text)
    df = df[df["player"] != ""]
    df = df[~df["player"].str.contains(r"team|totals|opponent|opponents|avg|average", case=False, na=False)]
    if df.empty:
        return None

    df["player_norm"] = df["player"].map(normalize_name)
    return df


def parse_stats_tables(stats_html):
    try:
        tables = pd.read_html(io.StringIO(stats_html))
    except Exception:
        return None, None

    field_candidates = []
    gk_candidates = []

    for raw_df in tables:
        df = clean_stats_df(raw_df)
        if df is None:
            continue

        cols = set(df.columns)
        if "player" not in cols:
            continue

        if len(cols & POSITION_BUCKETS["goalkeepers"]) >= 2:
            gk_candidates.append(df)
        if len(cols & POSITION_BUCKETS["forwards"]) >= 3:
            field_candidates.append(df)

    field_df = max(field_candidates, key=len) if field_candidates else None
    gk_df = max(gk_candidates, key=len) if gk_candidates else None
    return field_df, gk_df


def build_player_index(df):
    if df is None or df.empty:
        return {}

    index = {}
    for _, row in df.iterrows():
        full_name = row.get("player_norm", "")
        if not full_name:
            continue

        keys = {full_name}
        parts = full_name.split()
        if parts:
            keys.add(parts[-1])
            if len(parts) >= 2:
                keys.add(f"{parts[0]} {parts[-1]}")

        for key in keys:
            index.setdefault(key, []).append(row)

    return index


def find_matching_row(player_name, player_index):
    normalized = normalize_name(player_name)
    if not normalized:
        return None

    direct = player_index.get(normalized, [])
    if len(direct) == 1:
        return direct[0]

    parts = normalized.split()
    if len(parts) >= 2:
        first_last = f"{parts[0]} {parts[-1]}"
        first_last_matches = player_index.get(first_last, [])
        if len(first_last_matches) == 1:
            return first_last_matches[0]

        last_only = player_index.get(parts[-1], [])
        if len(last_only) == 1:
            return last_only[0]

    return None


def extract_field_stats(row):
    gp, gs = extract_gp_gs(row)
    return {
        "gp": gp,
        "gs": gs,
        "goals": safe_int(row.get("g", 0)),
        "assists": safe_int(row.get("a", 0)),
        "points": safe_int(row.get("pts", 0)),
        "shots": safe_int(row.get("sh", 0)),
    }


def extract_goalkeeper_stats(row):
    gp, gs = extract_gp_gs(row)
    return {
        "gp": gp,
        "gs": gs,
        "saves": safe_int(row.get("saves", 0)),
        "goals_against": safe_int(row.get("ga", 0)),
        "shutouts": safe_int(row.get("sho", row.get("sho/cbo", 0))),
    }


def validate_team_data(team_data):
    warnings = []
    players = team_data["players"]

    total_players = sum(len(group) for group in players.values())
    if total_players < 18:
        warnings.append(f"Only found {total_players} rostered players.")

    keeper_count = len(players["goalkeepers"])
    keeper_matches = sum(1 for p in players["goalkeepers"] if p.get("gp", 0) or p.get("saves", 0))
    if keeper_count and keeper_matches == 0:
        warnings.append("No goalkeeper stats matched any rostered goalkeeper.")

    bad_positions = []
    for category in players.values():
        for player in category:
            listed = player.get("listed_position", "")
            if re.search(r"(forwardorward|midfielderidfielder|defenderefender|goalkeeperoalkeeper)", listed, re.I):
                bad_positions.append(player["name"])
    if bad_positions:
        warnings.append("Some roster positions still look duplicated and should be checked.")

    return warnings


def build_team_data(school, roster_url, stats_url):
    print(f"\n--- Scraping {school} ---")
    team_data = {
        "school": school,
        "season": SEASON,
        "record": "0-0-0",
        "players": {"forwards": [], "midfielders": [], "defenders": [], "goalkeepers": []},
    }

    roster_url = seasonize_url(roster_url, "roster")
    stats_url = seasonize_url(stats_url, "stats")

    print(f"Fetching roster: {roster_url}")
    roster_html = fetch_page(roster_url)
    if not roster_html:
        return None, "Roster fetch failed", []

    roster_dict = parse_roster(roster_html)
    total_players = sum(len(roster_dict[cat]) for cat in roster_dict)
    if total_players < 11:
        return None, f"Failed: Only found {total_players} players. (Template mismatch)", []

    print(f"Fetching stats: {stats_url}")
    stats_html = fetch_page(stats_url)
    field_df, gk_df = (None, None)
    if stats_html:
        field_df, gk_df = parse_stats_tables(stats_html)

    field_index = build_player_index(field_df)
    gk_index = build_player_index(gk_df)

    status = "success"
    if field_df is None and gk_df is None:
        status = "missing_stats"

    field_matched = 0
    gk_matched = 0

    for category in ["forwards", "midfielders", "defenders"]:
        for player in roster_dict[category]:
            player.update({"gp": 0, "gs": 0, "goals": 0, "assists": 0, "points": 0, "shots": 0})
            row = find_matching_row(player["name"], field_index)
            if row is not None:
                player.update(extract_field_stats(row))
                field_matched += 1
            team_data["players"][category].append(player)

    for player in roster_dict["goalkeepers"]:
        player.update({"gp": 0, "gs": 0, "saves": 0, "shutouts": 0, "goals_against": 0})
        row = find_matching_row(player["name"], gk_index)
        if row is not None:
            player.update(extract_goalkeeper_stats(row))
            gk_matched += 1
        team_data["players"]["goalkeepers"].append(player)

    warnings = validate_team_data(team_data)
    if gk_df is not None and len(roster_dict["goalkeepers"]) > 0 and gk_matched == 0:
        warnings.append("Goalkeeper table was found, but no goalkeeper names matched.")
    if field_df is not None and field_matched == 0:
        warnings.append("Field-player table was found, but no outfield player names matched.")

    return team_data, status, warnings


def main():
    df = pd.read_csv(CSV_FILE, encoding="utf-8-sig")
    df.columns = df.columns.str.strip()
    batch_df = df.iloc[START_INDEX:] if BATCH_SIZE is None else df.iloc[START_INDEX:START_INDEX + BATCH_SIZE]
    print(
        f"Processing {len(batch_df)} team(s) from CSV rows "
        f"{START_INDEX + 1} to {START_INDEX + len(batch_df)}."
    )

    if os.path.exists(OUTPUT_JSON):
        with open(OUTPUT_JSON, "r", encoding="utf-8") as f:
            output = json.load(f)
    else:
        output = {
            "season": SEASON,
            "teams": [],
            "log": {"success": [], "missing_stats": [], "failed": [], "notes": {}, "warnings": {}},
        }

    output.setdefault("season", SEASON)
    output.setdefault("teams", [])
    output.setdefault("log", {})
    output["log"].setdefault("success", [])
    output["log"].setdefault("missing_stats", [])
    output["log"].setdefault("failed", [])
    output["log"].setdefault("notes", {})
    output["log"].setdefault("warnings", {})

    existing_teams = {team["school"]: team for team in output["teams"]}

    for _, row in batch_df.iterrows():
        school = row["School"]
        roster_url = row["Mens Soccer Roster URL"]
        stats_url = row["Mens Soccer Statistics URL"]

        if school in output["log"]["success"] or school in output["log"]["missing_stats"]:
            print(f"Skipping {school} - already processed.")
            continue

        result = build_team_data(school, roster_url, stats_url)
        team_data, status, warnings = result
        if team_data:
            existing_teams[school] = team_data

            if status == "success":
                output["log"]["success"].append(school)
            elif status == "missing_stats":
                output["log"]["missing_stats"].append(school)
                output["log"]["notes"][school] = (
                    "Roster scraped, but stats failed or the stats format still needs a custom parser."
                )

            if school in output["log"]["failed"]:
                output["log"]["failed"].remove(school)

            if warnings:
                output["log"]["warnings"][school] = warnings
        else:
            if school not in output["log"]["failed"]:
                output["log"]["failed"].append(school)
            output["log"]["notes"][school] = status

    output["teams"] = [existing_teams[school] for school in sorted(existing_teams)]

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nFull run complete! Check {OUTPUT_JSON} for the updated database.")


if __name__ == "__main__":
    main()
