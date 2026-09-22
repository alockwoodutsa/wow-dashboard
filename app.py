import os
import time
from urllib.parse import quote
from flask import Flask, render_template, request
import requests

app = Flask(__name__)

# Simple cache for API responses (expires after 5 minutes)
api_cache = {}
CACHE_DURATION = 300  # 5 minutes

CLIENT_ID = os.environ.get("CLIENT_ID")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET")

if not CLIENT_ID or not CLIENT_SECRET:
    raise RuntimeError("Missing CLIENT_ID or CLIENT_SECRET environment variables.")


def cached_request(url, headers=None, params=None):
    """Make a cached API request"""
    cache_key = f"{url}_{str(params)}_{str(headers)}"
    current_time = time.time()
    
    # Check if we have a cached response
    if cache_key in api_cache:
        cached_data, timestamp = api_cache[cache_key]
        if current_time - timestamp < CACHE_DURATION:
            return cached_data
    
    # Make the actual request
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            # Cache the successful response
            api_cache[cache_key] = (data, current_time)
            return data
        else:
            return None
    except:
        return None


def get_access_token():
    # Check cache first
    cache_key = "access_token"
    current_time = time.time()
    
    if cache_key in api_cache:
        token, timestamp = api_cache[cache_key]
        # Tokens are valid for 24 hours, but refresh every hour to be safe
        if current_time - timestamp < 3600:  # 1 hour
            return token
    
    # Get new token
    response = requests.post(
        "https://oauth.battle.net/token",
        data={"grant_type": "client_credentials"},
        auth=(CLIENT_ID, CLIENT_SECRET),
    )
    
    if response.status_code == 200:
        token = response.json()["access_token"]
        api_cache[cache_key] = (token, current_time)
        return token
    
    return None


def get_mythic_keystone_profile(realm, name):
    token = get_access_token()
    if not token:
        return None

    realm_slug = quote(realm.lower())
    character_name = quote(name.lower())
    url = f"https://us.api.blizzard.com/profile/wow/character/{realm_slug}/{character_name}/mythic-keystone-profile"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"namespace": "profile-us", "locale": "en_US"}

    return cached_request(url, headers=headers, params=params)


def get_character(realm, name):
    token = get_access_token()
    if not token:
        return {"profile": {}, "stats": {}}

    # Get character profile
    profile_url = f"https://us.api.blizzard.com/profile/wow/character/{realm}/{name}"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"namespace": "profile-us", "locale": "en_US"}
    
    profile_data = cached_request(profile_url, headers=headers, params=params) or {}
    
    # Get character stats
    stats_url = f"https://us.api.blizzard.com/profile/wow/character/{realm}/{name}/statistics"
    stats_data = cached_request(stats_url, headers=headers, params=params) or {}

    return {
        "profile": profile_data,
        "stats": stats_data
    }


@app.route("/", methods=["GET", "POST"])
def index():
    character = None
    error = None
   
    if request.method == "POST":
        name = request.form["name"]
        realm = request.form["realm"]
        
        data = get_character(realm, name)
        keystone_data = get_mythic_keystone_profile(realm, name)
        print("FORM SUBMITTED:", flush=True)
        print("DEBUG DATA:", data, flush=True)
        print("DEBUG KEYSTONE DATA:", keystone_data, flush=True)
        
        profile = data["profile"]
        stats = data["stats"]
       
        if not profile or "name" not in profile:
            error = "Character not found or API failed."
        else:
            # Parse stats directly from the response (they're top-level keys)
            stats_map = {}
            print("DEBUG STATS RESPONSE:", stats, flush=True)
            print("DEBUG STATS KEYS:", stats.keys() if isinstance(stats, dict) else "NOT A DICT", flush=True)
            
            # Extract effective values from top-level stat keys
            if isinstance(stats, dict):
                # Primary stats
                for stat_key in ['strength', 'agility', 'intellect']:
                    if stat_key in stats and isinstance(stats[stat_key], dict):
                        stats_map[stat_key] = stats[stat_key].get('effective', 0)
                
                # Secondary stats - map API keys to display names
                stat_mappings = {
                    'critical_strike': 'melee_crit',
                    'haste': 'melee_haste', 
                    'mastery': 'mastery',
                    'versatility': 'versatility',
                    'leech': 'lifesteal',
                    'avoidance': 'avoidance',
                    'speed': 'speed'
                }
                
                for display_key, api_key in stat_mappings.items():
                    if api_key in stats:
                        stat_data = stats[api_key]
                        if isinstance(stat_data, dict):
                            # For stats with 'value' field (crit, haste, mastery) - round to 2 decimal places
                            stats_map[display_key] = round(stat_data.get('value', 0), 2)
                        elif isinstance(stat_data, (int, float)):
                            # For direct numeric values (versatility, etc.) - round to 2 decimal places
                            stats_map[display_key] = round(stat_data, 2)
            
            print("DEBUG STATS MAP:", stats_map, flush=True)
            
            # Extract weekly mythic keystone runs
            weekly_runs = []
            total_weekly_runs = 0
            if isinstance(keystone_data, dict) and 'current_period' in keystone_data:
                current_period = keystone_data['current_period']
                if 'best_runs' in current_period:
                    for run in current_period['best_runs']:
                        dungeon_name = run.get('dungeon', {}).get('name', 'Unknown Dungeon')
                        keystone_level = run.get('keystone_level', 0)
                        weekly_runs.append({
                            'dungeon': dungeon_name,
                            'level': keystone_level
                        })
                        total_weekly_runs += 1
            
            # Determine the highest primary stat
            primary_stats = {
                "strength": stats_map.get("strength", 0),
                "agility": stats_map.get("agility", 0),
                "intellect": stats_map.get("intellect", 0)
            }
            highest_primary = max(primary_stats, key=primary_stats.get)
            
            character = {
                "name": profile.get("name"),
                "level": profile.get("level"),
                "ilvl": profile.get("equipped_item_level"),
                "highest_primary_stat": highest_primary,
                "highest_primary_value": primary_stats[highest_primary],
                "critical_strike": stats_map.get("critical_strike", 0),
                "haste": stats_map.get("haste", 0),
                "mastery": stats_map.get("mastery", 0),
                "versatility": stats_map.get("versatility", 0),
                "leech": stats_map.get("leech", 0),
                "avoidance": stats_map.get("avoidance", 0),
                "speed": stats_map.get("speed", 0),
                "weekly_runs": weekly_runs,
                "total_weekly_runs": total_weekly_runs
            }

    return render_template("index.html", character=character, error=error)


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/stats")
def stats():
    return render_template("stats.html")


@app.route("/history")
def history():
    return render_template("history.html")


@app.route("/guild", methods=["GET", "POST"])
def guild():
    guild_data = None
    error = None

    if request.method == "POST":
        guild_name = request.form["guild_name"]
        realm = request.form["realm"]
        
        # Convert spaces to dashes for Blizzard API
        guild_name_formatted = guild_name.replace(" ", "-").lower()

        try:
            # Get guild profile
            token = get_access_token()
            if not token:
                error = "Failed to get API access token"
            else:
                url = f"https://us.api.blizzard.com/data/wow/guild/{realm}/{guild_name_formatted}"
                headers = {"Authorization": f"Bearer {token}"}
                params = {"namespace": "profile-us", "locale": "en_US"}

                data = cached_request(url, headers=headers, params=params)

                if data:
                    # Get guild roster for member information
                    roster_url = f"https://us.api.blizzard.com/data/wow/guild/{realm}/{guild_name_formatted}/roster"
                    roster_data = cached_request(roster_url, headers=headers, params=params)

                    members = []
                    total_weekly_runs = 0
                    max_level_members = []
                    all_members = []

                    if roster_data:
                        all_members = roster_data.get("members", [])

                        # Get all max level characters (level 90)
                        max_level_members = [member for member in all_members 
                                           if member.get("character", {}).get("level", 0) >= 90]

                        # Calculate total weekly mythic+ runs from max level characters
                        # Limit to first 20 max level characters to avoid too many API calls
                        max_level_sample = max_level_members[:20]
                        for member in max_level_sample:
                            char = member.get("character", {})
                            char_name = char.get("name", "")
                            char_realm = char.get("realm", {}).get("slug", realm)

                            try:
                                # Fetch mythic keystone profile for this character
                                keystone_data = get_mythic_keystone_profile(char_realm, char_name)
                                if keystone_data and 'current_period' in keystone_data:
                                    current_period = keystone_data['current_period']
                                    if 'best_runs' in current_period:
                                        total_weekly_runs += len(current_period['best_runs'])
                            except:
                                # Skip characters that can't be fetched (private profiles, etc.)
                                continue

                        # Get member data with M+ ratings for sorting
                        # Only use max level members, and limit to first 50 to avoid excessive API calls
                        members_sample = max_level_members[:50]
                        members_with_ratings = []
                        for member in members_sample:
                            char = member.get("character", {})
                            char_name = char.get("name", "")
                            char_realm = char.get("realm", {}).get("slug", realm)
                            char_level = char.get("level", 0)

                            # Get M+ rating for this character
                            mythic_rating = 0
                            try:
                                keystone_data = get_mythic_keystone_profile(char_realm, char_name)
                                if keystone_data and 'current_mythic_rating' in keystone_data:
                                    mythic_rating = keystone_data['current_mythic_rating'].get('rating', 0)
                            except:
                                # If we can't fetch M+ data, rating stays 0
                                pass

                            members_with_ratings.append({
                                "name": char_name,
                                "level": char_level,
                                "rank": member.get("rank", 0),
                                "mythic_rating": mythic_rating
                            })

                        # Sort by mythic rating descending and take top 10
                        members_with_ratings.sort(key=lambda x: x['mythic_rating'], reverse=True)
                        members = members_with_ratings[:10]

                    guild_data = {
                        "name": data.get("name", "Unknown"),
                        "realm": data.get("realm", {}).get("name", realm),
                        "faction": data.get("faction", {}).get("name", "Unknown"),
                        "member_count": data.get("member_count", 0),
                        "achievement_points": data.get("achievement_points", 0),
                        "description": data.get("description", ""),
                        "guild_master": data.get("guild_master", {}).get("name", "Unknown"),
                        "top_members": members,
                        "total_weekly_runs": total_weekly_runs,
                        "max_level_count": len(max_level_members)
                    }
                else:
                    error = "Guild not found."

        except Exception as e:
            error = f"Error fetching guild data: {str(e)}"

    return render_template("guild.html", guild=guild_data, error=error)


if __name__ == "__main__":
    app.run(debug=True)