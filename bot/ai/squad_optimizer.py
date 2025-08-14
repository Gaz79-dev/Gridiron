from collections import defaultdict
from typing import List, Dict, Optional
import json

# Use absolute imports from the 'bot' package root
from bot.utils.database import Database, RsvpStatus
from bot.api.models import SquadBuildRequest

# --- Constants & Configuration ---

# Hell Let Loose class limits per squad
CLASS_LIMITS = {
    "Officer": 1, "Medic": 1, "Support": 1, "Anti-Tank": 1,
    "Machine Gunner": 1, "Automatic Rifleman": 1, "Assault": 1, "Engineer": 1,
    "Spotter": 1, "Sniper": 1, "Tank Commander": 1, "Commander": 1,
    "Rifleman": 99, "Crewman": 99,
}

# The order in which roles should be prioritized when filling squads.
ROLE_PRIORITY = [
    "Officer", "Support", "Medic", "Anti-Tank", "Machine Gunner", "Automatic Rifleman",
    "Engineer", "Assault", "Rifleman", "Tank Commander", "Crewman", "Spotter", "Sniper"
]

# --- AI Helper Functions ---

def _calculate_suitability_score(player_stats: Dict, target_squad_type: str, target_role: str) -> float:
    """
    Calculates a player's suitability for a specific role and squad type.
    """
    RATING_WEIGHT = 0.60
    SQUAD_AFFINITY_WEIGHT = 0.15
    ROLE_AFFINITY_WEIGHT = 0.25

    rating = player_stats.get('rating', 50)
    affinities = player_stats.get('role_affinities', {})
    squad_counts = affinities.get('squad_types', {})
    role_counts = affinities.get('roles', {})

    total_squad_placements = sum(squad_counts.values())
    squad_affinity = (squad_counts.get(target_squad_type, 0) / total_squad_placements) if total_squad_placements > 0 else 0

    total_role_placements = sum(role_counts.values())
    role_affinity = (role_counts.get(target_role, 0) / total_role_placements) if total_role_placements > 0 else 0

    suitability_score = (
        (rating * RATING_WEIGHT) +
        (squad_affinity * 100 * SQUAD_AFFINITY_WEIGHT) +
        (role_affinity * 100 * ROLE_AFFINITY_WEIGHT)
    )
    return suitability_score

def get_squad_iteration(squad_name: str, counts: Dict, convention: str, group_index: int) -> str:
    """Gets the next iteration for a squad name based on the convention."""
    counts[squad_name] = counts.get(squad_name, 0) + 1
    count = counts[squad_name]
    
    if convention == 'numeric':
        return f"{squad_name} ({group_index}.{count})"
    elif convention == 'alpha':
        iteration_char = chr(ord('A') + count - 1) if count <= 26 else f"Z{count - 26}"
        return f"{squad_name} {iteration_char}"
    else:
        return squad_name

# --- Main AI Drafting Logic ---

async def run_ai_draft(db: Database, event_id: int, request: SquadBuildRequest) -> List[Dict]:
    """
    The core logic for drafting players into squads, respecting player sign-up classes and squad limits.
    """
    # 1. SETUP: Clear old squads and get all necessary player data
    await db.delete_squads_for_event(event_id)
    signups = await db.get_signups_for_roster_page(event_id)
    
    player_pools = defaultdict(list)
    for signup in signups:
        if signup['rsvp_status'] == RsvpStatus.ACCEPTED:
            pool_key = signup.get('role_name') or "Unassigned"
            player_pools[pool_key].append(dict(signup))

    # 2. SQUAD DEFINITION: Create the empty squad structures from the template
    template = await db.get_squad_template_by_id(request.template_id)
    if not template:
        raise ValueError("Squad template not found.")
    
    squad_counts = {}
    squads_to_fill = []
    numeric_group_index = 1
    for definition in template['definitions']:
        squad_name = definition['squad_name']
        convention = definition['naming_convention']
        count = request.squad_counts.get(squad_name, 0)
        group_index_for_naming = numeric_group_index if convention == 'numeric' else 0

        for _ in range(count):
            full_squad_name = get_squad_iteration(squad_name, squad_counts, convention, group_index_for_naming)
            squads_to_fill.append({
                'name': full_squad_name,
                'squad_type': definition['squad_type'],
                'source_pool': definition['source_rsvp_pool'],
                'members': [],
                'class_counts': defaultdict(int)
            })
        
        if convention == 'numeric':
            numeric_group_index += 1

    # 3. DRAFTING PHASE: Place players based on their chosen class
    unplaced_players = []
    # Sort all players by role priority to place key roles first
    all_players_sorted = sorted(
        [p for pool in player_pools.values() for p in pool],
        key=lambda p: ROLE_PRIORITY.index(p.get('subclass_name')) if p.get('subclass_name') in ROLE_PRIORITY else 99
    )

    for player in all_players_sorted:
        player_placed = False
        player_class = player.get('subclass_name') or "Rifleman" # Default to Rifleman if no subclass
        
        # Find a squad that needs this player
        for squad in squads_to_fill:
            # Check if player is from the right RSVP pool and the squad isn't full
            squad_size = 6 if squad['squad_type'] == "Infantry" else 3 if squad['squad_type'] == "Armour" else 2
            if player.get('role_name') == squad['source_pool'] and len(squad['members']) < squad_size:
                # Check if the class slot is available in this squad
                if squad['class_counts'][player_class] < CLASS_LIMITS.get(player_class, 99):
                    squad['members'].append({'player_data': player, 'assigned_role': player_class})
                    squad['class_counts'][player_class] += 1
                    player_placed = True
                    break # Move to the next player
        
        if not player_placed:
            unplaced_players.append(player)
            
    # 4. FINALIZATION: Write the squads to the database
    for squad_data in squads_to_fill:
        squad_id = await db.create_squad(event_id, squad_data['name'], squad_data['squad_type'])
        for member_info in squad_data['members']:
            player = member_info['player_data']
            assigned_role = member_info['assigned_role']
            await db.add_squad_member(squad_id, int(player['user_id']), assigned_role)
    
    # 5. RESERVES: Add any unplaced players to the reserves squad
    if unplaced_players:
        reserves_id = await db.create_squad(event_id, "Reserves", "Reserves")
        for player in unplaced_players:
            role = player.get('subclass_name') or player.get('role_name') or 'Unassigned'
            await db.add_squad_member(reserves_id, int(player['user_id']), role)

    return await db.get_squads_with_members(event_id)
