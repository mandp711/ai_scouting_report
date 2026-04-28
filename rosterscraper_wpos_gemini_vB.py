import pandas as pd
import requests
import json
import time
import random
import io
import os
import re

# --- Configuration ---
CSV_FILE = "AI_soccer_urls.csv"
V1_JSON = "rosters_pos_stats_test2_gemini_full.json" 
OUTPUT_JSON = "rosters_pos_stats_V2.json" 
SEASON = "2025"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

def fetch_page(url):
    try:
        time.sleep(random.uniform(2.0, 4.0))
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        return response.text
    except Exception:
        return None

def safe_int(val):
    try:
        if pd.isna(val): return 0
        return int(float(val))
    except (ValueError, TypeError):
        return 0

def extract_gp_gs(row):
    gp_gs_col = next((c for c in row.index if 'gp' in c and 'gs' in c), None)
    if gp_gs_col and pd.notna(row[gp_gs_col]):
        parts = [p for p in re.split(r'\D+', str(row[gp_gs_col]).strip()) if p]
        gp = safe_int(parts[0]) if len(parts) > 0 else 0
        gs = safe_int(parts[1]) if len(parts) > 1 else 0
        return gp, gs
    
    gp_col = next((c for c in row.index if c in ['gp', 'games played']), None)
    gs_col = next((c for c in row.index if c in ['gs', 'games started']), None)
    
    gp = safe_int(row[gp_col]) if gp_col else 0
    gs = safe_int(row[gs_col]) if gs_col else 0
    return gp, gs

def map_position(raw_pos_string):
    if not raw_pos_string: return "midfielders" 
    primary = re.split(r'[/,\-]', str(raw_pos_string))[0].strip().upper()
    if primary.startswith('F') or primary == 'STR' or 'FORWARD' in primary: return "forwards"
    elif primary.startswith('M'): return "midfielders"
    elif primary.startswith('D') or primary.startswith('B') or 'BACK' in primary: return "defenders"
    elif primary.startswith('G'): return "goalkeepers"
    else: return "midfielders"

def parse_roster_table(html):
    roster_dict = {"forwards": [], "midfielders": [], "defenders": [], "goalkeepers": []}
    try:
        tables = pd.read_html(io.StringIO(html))
        roster_df = None
        for df in tables:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(-1)
            cols = df.columns.astype(str).str.lower().str.strip().tolist()
            if any(c in cols for c in ['name', 'player', 'full name']) and any(c in cols for c in ['pos', 'position', 'pos.']):
                roster_df = df
                break
        
        if roster_df is None or roster_df.empty: return None
            
        roster_df.columns = roster_df.columns.astype(str).str.lower().str.strip()
        name_col = next((c for c in roster_df.columns if c in ['name', 'player', 'full name']), None)
        pos_col = next((c for c in roster_df.columns if c in ['pos', 'position', 'pos.']), None)
        num_col = next((c for c in roster_df.columns if c in ['#', 'no', 'no.', 'number']), None)
        
        for _, row in roster_df.iterrows():
            name = str(row[name_col]).strip() if name_col and pd.notna(row[name_col]) else "Unknown"
            if name == "Unknown" or str(name).lower() == "nan": continue
            
            words = name.split()
            half = len(words) // 2
            if len(words) > 1 and len(words) % 2 == 0 and words[:half] == words[half:]:
                name = " ".join(words[:half])
            
            raw_pos = str(row[pos_col]).strip() if pos_col and pd.notna(row[pos_col]) else "M"
            raw_pos = re.sub(r'(?i)^(pos\.?|position)[:\s]*', '', raw_pos).strip()
            
            number = "NA"
            if num_col and pd.notna(row[num_col]):
                try:
                    number = int(float(str(row[num_col]).strip()))
                except (ValueError, TypeError):
                    num_val = str(row[num_col]).strip()
                    num_digits = re.sub(r'\D', '', num_val)
                    number = safe_int(num_digits) if num_digits else num_val
                
            clean_pos = raw_pos.replace("ForwardF", "Forward").replace("MidfielderM", "Midfielder").replace("DefenderD", "Defender").replace("GoalkeeperGK", "Goalkeeper")
            bucket = map_position(clean_pos)
            
            roster_dict[bucket].append({"name": name, "number": number, "listed_position": clean_pos})
            
        return roster_dict
    except Exception:
        return None

def parse_stats_tables(stats_html):
    try:
        tables = pd.read_html(io.StringIO(stats_html))
        field_df, gk_df = None, None
        for df in tables:
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(-1)
            df.columns = df.columns.astype(str).str.lower().str.strip()
            df = df.loc[:, ~df.columns.duplicated()]
            cols = df.columns.tolist()
            
            # --- THE FIX: ADDED DYNAMIC COLUMN MATCHING ---
            if field_df is None and any(c in cols for c in ['player', 'name']) and 'g' in cols and any(c in cols for c in ['pts', 'points']):
                field_df = df
            elif gk_df is None and any(c in cols for c in ['player', 'name', 'goalie', 'goalkeeper', 'goalkeepers']) and any(c in cols for c in ['saves', 'sv', 'svs']):
                gk_df = df
                
            if field_df is not None and gk_df is not None: break
        return field_df, gk_df
    except Exception:
        return None, None

def build_team_data(school, roster_url, stats_url):
    print(f"\n--- Scraping {school} (V2 Table Method) ---")
    team_data = {"school": school, "season": SEASON, "record": "0-0-0", "players": {"forwards": [], "midfielders": [], "defenders": [], "goalkeepers": []}}
    
    print(f"Fetching roster...")
    roster_html = fetch_page(roster_url)
    if not roster_html: return None, "Roster fetch failed"
    
    roster_dict = parse_roster_table(roster_html)
    if not roster_dict: return None, "Failed: Could not find a valid Roster Table."
        
    total_players = sum(len(roster_dict[cat]) for cat in roster_dict)
    if total_players < 11: return None, f"Failed: Only found {total_players} players in table."
    
    print(f"Fetching stats...")
    stats_html = fetch_page(stats_url)
    field_df, gk_df = None, None
    if stats_html:
        field_df, gk_df = parse_stats_tables(stats_html)
        
    status = "success"
    if field_df is None and gk_df is None:
        status = "missing_stats"
    
    for category in ["forwards", "midfielders", "defenders"]:
        for p in roster_dict[category]:
            clean_name = p["name"].replace(",", "")
            last_name = clean_name.split()[-1] if " " in clean_name else clean_name
            
            p.update({"gp": 0, "gs": 0, "goals": 0, "assists": 0, "points": 0, "shots": 0})
            if field_df is not None:
                name_col = next((c for c in field_df.columns if c in ['player', 'name']), None)
                match = pd.DataFrame()
                if name_col:
                    match = field_df[field_df[name_col].str.contains(last_name, case=False, na=False)]
                
                if not match.empty:
                    row = match.iloc[0]
                    p["gp"], p["gs"] = extract_gp_gs(row)
                    p["goals"] = safe_int(row.get('g', 0))
                    p["assists"] = safe_int(row.get('a', 0))
                    p["points"] = safe_int(row.get('pts', row.get('points', 0)))
                    p["shots"] = safe_int(row.get('sh', row.get('shots', 0)))
            team_data["players"][category].append(p)
            
    for p in roster_dict["goalkeepers"]:
        clean_name = p["name"].replace(",", "")
        last_name = clean_name.split()[-1] if " " in clean_name else clean_name
        p.update({"gp": 0, "gs": 0, "saves": 0, "shutouts": 0, "goals_against": 0})
        if gk_df is not None:
            # --- THE FIX: GOALIE COLUMN HUNTER ---
            name_col = next((c for c in gk_df.columns if c in ['player', 'name', 'goalie', 'goalkeeper', 'goalkeepers']), None)
            match = pd.DataFrame()
            if name_col:
                match = gk_df[gk_df[name_col].str.contains(last_name, case=False, na=False)]
                
            if not match.empty:
                row = match.iloc[0]
                p["gp"], p["gs"] = extract_gp_gs(row)
                p["saves"] = safe_int(row.get('saves', row.get('sv', row.get('svs', 0))))
                p["goals_against"] = safe_int(row.get('ga', 0))
                p["shutouts"] = safe_int(row.get('sho', row.get('sho/cbo', 0)))
        team_data["players"]["goalkeepers"].append(p)
            
    return team_data, status

def main():
    if not os.path.exists(V1_JSON):
        print(f"Error: Could not find {V1_JSON}.")
        return
        
    with open(V1_JSON, "r", encoding="utf-8") as f:
        v1_data = json.load(f)
        
    failed_teams_list = v1_data["log"].get("failed", [])
    df = pd.read_csv(CSV_FILE, encoding='utf-8-sig')
    df.columns = df.columns.str.strip()
    
    batch_df = df[df['School'].isin(failed_teams_list)]
    
    if os.path.exists(OUTPUT_JSON):
        with open(OUTPUT_JSON, "r", encoding="utf-8") as f:
            output = json.load(f)
    else:
        output = {"season": SEASON, "teams": [], "log": {"success": [], "missing_stats": [], "failed": [], "notes": {}}}
    
    for _, row in batch_df.iterrows():
        school, roster_url, stats_url = row['School'], row['Mens Soccer Roster URL'], row['Mens Soccer Statistics URL']
        
        roster_url = str(roster_url).strip()
        if not roster_url.endswith("2025"):
            roster_url = roster_url.rstrip("/") + "/2025"
            
        if school in output["log"]["success"] or school in output["log"]["missing_stats"]:
            print(f"Skipping {school} - already processed in V2.")
            continue
            
        team_data, status = build_team_data(school, roster_url, stats_url)
        
        if team_data:
            output["teams"].append(team_data)
            if status == "success":
                output["log"]["success"].append(school)
            elif status == "missing_stats":
                output["log"]["missing_stats"].append(school)
                output["log"]["notes"][school] = "Roster scraped via V2 table, but stats failed."
                
            if school in output["log"]["failed"]:
                output["log"]["failed"].remove(school)
        else:
            if school not in output["log"]["failed"]:
                output["log"]["failed"].append(school)
            output["log"]["notes"][school] = status
            
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
        
    print(f"\nV2 Run complete! Check {OUTPUT_JSON} for the rescued teams.")

if __name__ == "__main__":
    main()