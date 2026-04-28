import pandas as pd
import requests
from bs4 import BeautifulSoup
import json
import time
import random
import io
import os
import re


# --- Configuration ---
CSV_FILE = "AI_soccer_urls.csv"
OUTPUT_JSON = "rosters_pos_stats_test2_gemini_full.json"
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


def parse_roster(html):
   soup = BeautifulSoup(html, "html.parser")
   roster_dict = {"forwards": [], "midfielders": [], "defenders": [], "goalkeepers": []}
   roster_cards = soup.find_all(class_=re.compile(r'sidearm-roster-player$'))
  
   for card in roster_cards:
       try:
           name_tag = card.find(class_="sidearm-roster-player-name")
           name = "Unknown"
           if name_tag:
               a_tag = name_tag.find("a")
               name = a_tag.get_text(strip=True) if a_tag else name_tag.get_text(strip=True).replace(card.find(class_="sidearm-roster-player-jersey-number").get_text(strip=True) if card.find(class_="sidearm-roster-player-jersey-number") else "", "")
          
           number_tag = card.find(class_="sidearm-roster-player-jersey-number")
           number = number_tag.get_text(strip=True) if number_tag else "NA"
          
           position_tag = card.find(class_="sidearm-roster-player-position")
           raw_pos = position_tag.find("span").get_text(strip=True) if position_tag and position_tag.find("span") else (position_tag.get_text(strip=True) if position_tag else "Midfielder")
              
           clean_pos = str(raw_pos).replace("ForwardF", "Forward").replace("MidfielderM", "Midfielder").replace("DefenderD", "Defender").replace("GoalkeeperGK", "Goalkeeper").replace("GoalkeeperG", "Goalkeeper")
          
           bucket = map_position(clean_pos)
           roster_dict[bucket].append({"name": name, "number": safe_int(number) if str(number).isdigit() else number, "listed_position": clean_pos})
       except Exception:
           continue
   return roster_dict


def parse_stats_tables(stats_html):
   try:
       tables = pd.read_html(io.StringIO(stats_html))
       field_df, gk_df = None, None
       for df in tables:
           if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(-1)
           df.columns = df.columns.astype(str).str.lower().str.strip()
           df = df.loc[:, ~df.columns.duplicated()]
           cols = df.columns.tolist()
           if field_df is None and ('player' in cols or 'name' in cols) and 'g' in cols and ('pts' in cols or 'points' in cols):
               field_df = df
           elif gk_df is None and ('player' in cols or 'name' in cols) and ('saves' in cols or 'sv' in cols):
               gk_df = df
           if field_df is not None and gk_df is not None: break
       return field_df, gk_df
   except Exception:
       return None, None


def build_team_data(school, roster_url, stats_url):
   print(f"\n--- Scraping {school} ---")
   team_data = {"school": school, "season": SEASON, "record": "0-0-0", "players": {"forwards": [], "midfielders": [], "defenders": [], "goalkeepers": []}}
  
   print(f"Fetching roster...")
   roster_html = fetch_page(roster_url)
   if not roster_html: return None, "Roster fetch failed"
  
   roster_dict = parse_roster(roster_html)
  
   # --- BULLETPROOF ROSTER CHECK ---
   total_players = sum(len(roster_dict[cat]) for cat in roster_dict)
   if total_players < 11:
       return None, f"Failed: Only found {total_players} players. (Template mismatch)"
  
   print(f"Fetching stats...")
   stats_html = fetch_page(stats_url)
   field_df, gk_df = None, None
   if stats_html:
       field_df, gk_df = parse_stats_tables(stats_html)
      
   # --- STATS STATUS CHECK ---
   status = "success"
   if field_df is None and gk_df is None:
       status = "missing_stats"
  
   for category in ["forwards", "midfielders", "defenders"]:
       for p in roster_dict[category]:
           last_name = p["name"].split()[-1] if " " in p["name"] else p["name"]
           p.update({"gp": 0, "gs": 0, "goals": 0, "assists": 0, "points": 0, "shots": 0})
           if field_df is not None:
               match = field_df[field_df['player'].str.contains(last_name, case=False, na=False)] if 'player' in field_df.columns else pd.DataFrame()
               if not match.empty:
                   row = match.iloc[0]
                   p["gp"], p["gs"] = extract_gp_gs(row)
                   p["goals"] = safe_int(row.get('g', 0))
                   p["assists"] = safe_int(row.get('a', 0))
                   p["points"] = safe_int(row.get('pts', row.get('points', 0)))
                   p["shots"] = safe_int(row.get('sh', row.get('shots', 0)))
           team_data["players"][category].append(p)
          
   for p in roster_dict["goalkeepers"]:
       last_name = p["name"].split()[-1] if " " in p["name"] else p["name"]
       p.update({"gp": 0, "gs": 0, "saves": 0, "shutouts": 0, "goals_against": 0})
       if gk_df is not None:
           match = gk_df[gk_df['player'].str.contains(last_name, case=False, na=False)] if 'player' in gk_df.columns else pd.DataFrame()
           if not match.empty:
               row = match.iloc[0]
               p["gp"], p["gs"] = extract_gp_gs(row)
               p["saves"] = safe_int(row.get('saves', row.get('sv', 0)))
               p["goals_against"] = safe_int(row.get('ga', 0))
               p["shutouts"] = safe_int(row.get('sho', row.get('sho/cbo', 0)))
       team_data["players"]["goalkeepers"].append(p)
          
   return team_data, status


def main():
   df = pd.read_csv(CSV_FILE, encoding='utf-8-sig')
   df.columns = df.columns.str.strip()
  
   # The "Let It Rip" mode: process every row in the CSV
   batch_df = df
  
   if os.path.exists(OUTPUT_JSON):
       with open(OUTPUT_JSON, "r", encoding="utf-8") as f:
           output = json.load(f)
   else:
       output = {"season": SEASON, "teams": [], "log": {"success": [], "missing_stats": [], "failed": [], "notes": {}}}
  
   for _, row in batch_df.iterrows():
       school, roster_url, stats_url = row['School'], row['Mens Soccer Roster URL'], row['Mens Soccer Statistics URL']
      
       # Skip if completely successful or already flagged for missing stats
       if school in output["log"]["success"] or school in output["log"]["missing_stats"]:
           print(f"Skipping {school} - already processed.")
           continue
          
       team_data, status = build_team_data(school, roster_url, stats_url)
      
       if team_data:
           output["teams"].append(team_data)
           if status == "success":
               output["log"]["success"].append(school)
           elif status == "missing_stats":
               output["log"]["missing_stats"].append(school)
               output["log"]["notes"][school] = "Roster scraped, but stats failed (Dynamic JavaScript or different format)."
              
           if school in output["log"]["failed"]:
               output["log"]["failed"].remove(school)
       else:
           if school not in output["log"]["failed"]:
               output["log"]["failed"].append(school)
           output["log"]["notes"][school] = status
          
   with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
       json.dump(output, f, indent=2, ensure_ascii=False)
      
   print(f"\nFull run complete! Check {OUTPUT_JSON} for the final database.")


if __name__ == "__main__":
   main()

