"""
NCAA D1 Soccer Roster Scraper
Scrapes player rosters from athletic department websites and outputs clean JSON.
Handles common platforms like Sidearm Sports, PrestoSports, and custom sites.
"""

import requests
from bs4 import BeautifulSoup
import json
import time
import re
from typing import List, Dict, Optional

# User-Agent to avoid basic bot blocking
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def clean_text(text: str) -> str:
    """Clean up whitespace and special characters from scraped text"""
    if not text:
        return ""
    return re.sub(r'\s+', ' ', text.strip())

def parse_position(pos_text: str) -> tuple:
    """
    Parse position text into primary position and sub-position.
    Returns (position, sub_position)
    Examples: "Forward" -> ("FWD", "ST")
              "Midfielder/Defender" -> ("MID", "CM")
              "GK" -> ("GK", "GK")
    """
    pos_text = clean_text(pos_text).upper()
    
    # Position mapping
    if 'GOAL' in pos_text or pos_text == 'GK':
        return ('GK', 'GK')
    elif 'FORWARD' in pos_text or pos_text in ['F', 'FW', 'ST', 'STRIKER']:
        return ('FWD', 'ST')
    elif 'MID' in pos_text or pos_text in ['M', 'MF']:
        return ('MID', 'CM')
    elif 'DEF' in pos_text or pos_text in ['D', 'DF', 'BACK']:
        return ('DEF', 'CB')
    else:
        # Default to midfielder if unclear
        return ('MID', 'CM')

def parse_height(height_text: str) -> Optional[str]:
    """Parse height in various formats to feet-inches"""
    if not height_text:
        return None
    height_text = clean_text(height_text)
    # Match patterns like 6-2, 6'2", 6-2, etc.
    match = re.search(r"(\d+)['\-\s]*(\d+)", height_text)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    return None

def parse_class_year(year_text: str) -> Optional[str]:
    """Parse class year (Fr, So, Jr, Sr)"""
    if not year_text:
        return None
    year_text = clean_text(year_text).upper()
    if 'FR' in year_text or 'FRESHMAN' in year_text:
        return 'Fr'
    elif 'SO' in year_text or 'SOPHOMORE' in year_text:
        return 'So'
    elif 'JR' in year_text or 'JUNIOR' in year_text:
        return 'Jr'
    elif 'SR' in year_text or 'SENIOR' in year_text:
        return 'Sr'
    return year_text[:2] if len(year_text) >= 2 else None

def scrape_sidearm_roster(url: str, team_name: str) -> Optional[List[Dict]]:
    """
    Scrape roster from Sidearm Sports platform (most common NCAA platform).
    Used by 70-80% of D1 programs.
    """
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        roster = []
        seen_players = set()  # Track unique players to avoid duplicates
        
        # Sidearm typically uses a table with class "roster" or similar
        # Try multiple selectors
        table = (soup.find('table', class_=re.compile(r'roster', re.I)) or 
                soup.find('div', class_=re.compile(r'roster', re.I)) or
                soup.find('table', id=re.compile(r'roster', re.I)))
        
        if not table:
            print(f"  ⚠ Warning: Could not find roster table on {team_name}")
            return None
        
        # Find all player rows (tr elements or roster-player divs)
        rows = table.find_all('tr')[1:]  # Skip header
        if not rows:
            # Try div-based layout
            rows = soup.find_all('div', class_=re.compile(r'roster-player|player-card', re.I))
        
        for row in rows:
            try:
                # Extract data - Sidearm uses various structures
                # Try table-based first
                cells = row.find_all('td')
                jersey = None
                name = None
                position = ""
                height = None
                year = None
                hometown = None
                
                if cells and len(cells) >= 2:
                    # Typical columns: # | Name | Pos | Ht | Yr | Hometown
                    jersey_text = clean_text(cells[0].get_text())
                    name = clean_text(cells[1].get_text())
                    position = clean_text(cells[2].get_text()) if len(cells) > 2 else ""
                    height = parse_height(cells[3].get_text()) if len(cells) > 3 else None
                    year = parse_class_year(cells[4].get_text()) if len(cells) > 4 else None
                    hometown = clean_text(cells[5].get_text()) if len(cells) > 5 else None
                    
                    # Parse jersey - remove if it's in the name
                    jersey_match = re.search(r'^\s*(\d+)\s*$', jersey_text)
                    if jersey_match:
                        jersey = int(jersey_match.group(1))
                    else:
                        # Sometimes jersey is part of name cell
                        name_match = re.search(r'^(\d+)\s+(.+)$', name)
                        if name_match:
                            jersey = int(name_match.group(1))
                            name = name_match.group(2)
                else:
                    # Try div-based extraction
                    jersey_el = row.find(class_=re.compile(r'number|jersey', re.I))
                    name_el = row.find(class_=re.compile(r'name', re.I))
                    pos_el = row.find(class_=re.compile(r'position|pos', re.I))
                    height_el = row.find(class_=re.compile(r'height|ht', re.I))
                    year_el = row.find(class_=re.compile(r'year|class', re.I))
                    hometown_el = row.find(class_=re.compile(r'hometown|home', re.I))
                    
                    if not name_el:
                        continue
                    
                    jersey_text = clean_text(jersey_el.get_text()) if jersey_el else ""
                    name = clean_text(name_el.get_text())
                    position = clean_text(pos_el.get_text()) if pos_el else ""
                    height = parse_height(height_el.get_text()) if height_el else None
                    year = parse_class_year(year_el.get_text()) if year_el else None
                    hometown = clean_text(hometown_el.get_text()) if hometown_el else None
                    
                    jersey_match = re.search(r'\d+', jersey_text)
                    if jersey_match:
                        jersey = int(jersey_match.group())
                
                if not name or not name.strip():
                    continue
                
                # Remove jersey number from name if it snuck in
                name = re.sub(r'^\d+\s+', '', name)
                
                # Create unique key to check for duplicates
                player_key = f"{name}_{jersey}_{position}"
                if player_key in seen_players:
                    continue
                seen_players.add(player_key)
                
                # Split name into first/last
                name_parts = name.split()
                if len(name_parts) >= 2:
                    first_name = name_parts[0]
                    last_name = ' '.join(name_parts[1:])
                elif len(name_parts) == 1:
                    first_name = name_parts[0]
                    last_name = ""
                else:
                    continue
                
                # Parse position
                pos, sub_pos = parse_position(position)
                
                player = {
                    'jersey': jersey,
                    'firstName': first_name,
                    'lastName': last_name,
                    'position': pos,
                    'subPosition': sub_pos,
                    'height': height,
                    'year': year,
                    'hometown': hometown
                }
                
                roster.append(player)
                
            except Exception as e:
                print(f"  ⚠ Error parsing player row: {e}")
                continue
        
        return roster if roster else None
        
    except requests.RequestException as e:
        print(f"  ✗ Failed to fetch {team_name}: {e}")
        return None
    except Exception as e:
        print(f"  ✗ Error parsing {team_name}: {e}")
        return None

def scrape_generic_roster(url: str, team_name: str) -> Optional[List[Dict]]:
    """
    Generic fallback scraper for non-Sidearm sites.
    Attempts to find roster data using common HTML patterns.
    """
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        roster = []
        
        # Look for any table or list structure
        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')[1:]  # Skip header
            
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 2:
                    # Heuristic: look for name pattern
                    text = ' '.join([clean_text(c.get_text()) for c in cells])
                    # Skip if it doesn't look like a player row
                    if not re.search(r'[A-Z][a-z]+\s+[A-Z][a-z]+', text):
                        continue
                    
                    # Try to extract basic info
                    jersey = clean_text(cells[0].get_text())
                    jersey_num = None
                    if jersey and jersey.isdigit():
                        jersey_num = int(jersey)
                    
                    # Name is usually in first or second column
                    name_idx = 1 if jersey_num else 0
                    name = clean_text(cells[name_idx].get_text())
                    
                    name_parts = name.split()
                    if len(name_parts) >= 2:
                        first_name = name_parts[0]
                        last_name = ' '.join(name_parts[1:])
                    else:
                        continue
                    
                    # Try to find position
                    position = ""
                    for cell in cells[name_idx+1:]:
                        cell_text = clean_text(cell.get_text())
                        if any(pos in cell_text.upper() for pos in ['GK', 'GOAL', 'FORWARD', 'MID', 'DEF', 'F', 'M', 'D']):
                            position = cell_text
                            break
                    
                    pos, sub_pos = parse_position(position)
                    
                    player = {
                        'jersey': jersey_num,
                        'firstName': first_name,
                        'lastName': last_name,
                        'position': pos,
                        'subPosition': sub_pos,
                        'height': None,
                        'year': None,
                        'hometown': None
                    }
                    
                    roster.append(player)
        
        return roster if roster else None
        
    except Exception as e:
        print(f"  ✗ Generic scraper failed for {team_name}: {e}")
        return None

def scrape_roster(url: str, team_name: str) -> Optional[List[Dict]]:
    """
    Main scraper function that tries different strategies.
    """
    print(f"📥 Scraping {team_name}...")
    
    # Special case handlers for known problematic sites
    if 'virginia' in url.lower() and 'virginiasports' in url:
        # Virginia uses a unique layout
        roster = scrape_virginia_custom(url, team_name)
        if roster:
            return roster
    
    # Try Sidearm scraper first (most common)
    roster = scrape_sidearm_roster(url, team_name)
    
    # If Sidearm fails, try generic scraper
    if not roster:
        print(f"  ↻ Trying generic scraper...")
        roster = scrape_generic_roster(url, team_name)
    
    if roster:
        print(f"  ✓ Found {len(roster)} players")
    else:
        print(f"  ✗ No roster data found")
    
    return roster

def scrape_virginia_custom(url: str, team_name: str) -> Optional[List[Dict]]:
    """Custom scraper for Virginia's specific site structure"""
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        roster = []
        seen_players = set()
        
        # Virginia uses roster-card divs
        cards = soup.find_all('li', class_=re.compile(r'roster-card|player-card', re.I))
        
        if not cards:
            # Try alternative structure
            cards = soup.find_all('div', class_=re.compile(r'roster-player', re.I))
        
        for card in cards:
            try:
                # Extract jersey
                jersey_el = card.find(class_=re.compile(r'number|jersey', re.I))
                jersey = None
                if jersey_el:
                    jersey_match = re.search(r'\d+', jersey_el.get_text())
                    if jersey_match:
                        jersey = int(jersey_match.group())
                
                # Extract name
                name_el = card.find(class_=re.compile(r'name', re.I)) or card.find('h3') or card.find('h2')
                if not name_el:
                    continue
                
                name = clean_text(name_el.get_text())
                name = re.sub(r'^\d+\s+', '', name)  # Remove jersey if in name
                
                # Extract position
                pos_el = card.find(class_=re.compile(r'position|pos', re.I))
                position = clean_text(pos_el.get_text()) if pos_el else ""
                
                # Deduplicate
                player_key = f"{name}_{jersey}"
                if player_key in seen_players:
                    continue
                seen_players.add(player_key)
                
                # Parse name
                name_parts = name.split()
                if len(name_parts) >= 2:
                    first_name = name_parts[0]
                    last_name = ' '.join(name_parts[1:])
                else:
                    continue
                
                pos, sub_pos = parse_position(position)
                
                roster.append({
                    'jersey': jersey,
                    'firstName': first_name,
                    'lastName': last_name,
                    'position': pos,
                    'subPosition': sub_pos,
                    'height': None,
                    'year': None,
                    'hometown': None
                })
            except Exception as e:
                continue
        
        return roster if roster else None
        
    except Exception as e:
        print(f"  ✗ Virginia custom scraper failed: {e}")
        return None

def main():
    """
    Main function - edit the TEAMS list below with your roster URLs
    """
    
    # ========================================================================
    # EDIT THIS SECTION - Add your team roster URLs here
    # ========================================================================
    TEAMS = [
        {"name": "Washington Huskies", "url": "https://gohuskies.com/sports/mens-soccer/roster"},
        {"name": "Princeton Tigers", "url": "https://goprincetontigers.com/sports/mens-soccer/roster"},
        {"name": "NC State Wolfpack", "url": "https://gopack.com/sports/mens-soccer/roster"},
        {"name": "Vermont Catamounts", "url": "https://uvmathletics.com/sports/mens-soccer/roster"},
        {"name": "Virginia Cavaliers", "url": "https://virginiasports.com/sports/mens-soccer/roster"},
        {"name": "Bryant Bulldogs", "url": "https://bryantbulldogs.com/sports/mens-soccer/roster"},
        {"name": "SMU Mustangs", "url": "https://smumustangs.com/sports/mens-soccer/roster"},
        {"name": "Maryland Terrapins", "url": "https://umterps.com/sports/mens-soccer/roster"},
        {"name": "San Diego Toreros", "url": "https://usdtoreros.com/sports/mens-soccer/roster"},
        {"name": "Portland Pilots", "url": "https://portlandpilots.com/sports/mens-soccer/roster"},
        {"name": "Georgetown Hoyas", "url": "https://guhoyas.com/sports/mens-soccer/roster"},
        {"name": "Saint Louis Billikens", "url": "https://slubillikens.com/sports/mens-soccer/roster"},
        {"name": "Hofstra Pride", "url": "https://gohofstra.com/sports/mens-soccer/roster"},
        {"name": "Furman Paladins", "url": "https://furmanpaladins.com/sports/mens-soccer/roster"},
        {"name": "High Point Panthers", "url": "https://highpointpanthers.com/sports/mens-soccer/roster"},
        {"name": "Akron Zips", "url": "https://gozips.com/sports/mens-soccer/roster"},
        {"name": "Stanford Cardinal", "url": "https://gostanford.com/sports/mens-soccer/roster"},
        {"name": "Indiana Hoosiers", "url": "https://iuhoosiers.com/sports/mens-soccer/roster"},
        {"name": "Connecticut Huskies", "url": "https://uconnhuskies.com/sports/mens-soccer/roster"},
        {"name": "Denver Pioneers", "url": "https://denverpioneers.com/sports/mens-soccer/roster"},
        {"name": "Duke Blue Devils", "url": "https://goduke.com/sports/mens-soccer/roster"},
        {"name": "Marshall Thundering Herd", "url": "https://herdzone.com/sports/mens-soccer/roster"},
        {"name": "Kansas City Roos", "url": "https://gokangaroos.com/sports/mens-soccer/roster"},
        {"name": "West Virginia Mountaineers", "url": "https://wvusports.com/sports/mens-soccer/roster"},
        {"name": "North Carolina Tar Heels", "url": "https://goheels.com/sports/mens-soccer/roster"},
    ]
    # ========================================================================
    
    print("=" * 60)
    print("NCAA D1 Soccer Roster Scraper")
    print("=" * 60)
    print(f"\nScraping {len(TEAMS)} teams...\n")
    
    all_rosters = {}
    success_count = 0
    
    for team in TEAMS:
        roster = scrape_roster(team['url'], team['name'])
        
        if roster:
            all_rosters[team['name']] = roster
            success_count += 1
        else:
            all_rosters[team['name']] = []
        
        # Be polite - add delay between requests
        time.sleep(1)
    
    # Save to JSON file
    output_file = 'rosters.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_rosters, f, indent=2, ensure_ascii=False)
    
    print("\n" + "=" * 60)
    print(f"✓ Scraping complete!")
    print(f"  Successfully scraped: {success_count}/{len(TEAMS)} teams")
    print(f"  Output saved to: {output_file}")
    print("=" * 60)
    
    # Print summary
    print("\nRoster sizes:")
    for team_name, roster in all_rosters.items():
        status = "✓" if roster else "✗"
        print(f"  {status} {team_name}: {len(roster)} players")

if __name__ == "__main__":
    main()