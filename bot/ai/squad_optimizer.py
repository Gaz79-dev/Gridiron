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
    "Spotter": 1, "Sniper": 1, "Tank Commander": 1,
    "Rifleman": 99, "Crewman": 99, "Commander": 1,
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
    The core logic for drafting players into squads using a rule-first, AI-optimized approach.
    """
    # 1. SETUP: Clear old squads and get all necessary player data
    await db.delete_squads_for_event(event_id)
    
    signups = await db.get_signups_for_event(event_id)
    player_stats_records = await db.get_all_player_stats_for_admin()
    player_stats_map = {str(p['user_id']): p for p in player_stats_records}

    # --- FIX START: Pre-filter players into pools based on their chosen sign-up role ---
    player_pools = defaultdict(list)
    for signup in signups:
        if signup['rsvp_status'] == RsvpStatus.ACCEPTED:
            # The key is the primary role they signed up for (e.g., "Infantry", "Commander")
            pool_key = signup.get('role_name') or "Unassigned"
            player_pools[pool_key].append(dict(signup))
    # --- FIX END ---

    # 2. SQUAD DEFINITION: Build the list of squads to be filled
    template = await db.get_squad_template_by_id(request.template_id)
    if not template:
        raise ValueError("Squad template not found.")
    
    squad_counts, squads_to_fill = {}, []
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
                'source_pool': definition['source_rsvp_pool'], # This is the crucial link
                'members': [],
                'class_counts': defaultdict(int)
            })
        
        if convention == 'numeric':
            numeric_group_index += 1

    # 3. DRAFTING PHASE: Fill squads using rule-based pools and AI optimization
    unplaced_players = []

    for squad in squads_to_fill:
        # --- FIX: The AI now ONLY considers players from the correct sign-up pool ---
        eligible_players = player_pools[squad['source_pool']]
        
        squad_size = 1 if squad['squad_type'] == "Command" else \
                     3 if squad['squad_type'] == "Armour" else \
                     2 if squad['squad_type'] in ["Recon", "Artillery"] else 6

        # For Command squads, the role is fixed
        if squad['squad_type'] == "Command":
            roles_to_fill = ["Commander"]
        else:
            roles_to_fill = [role for role in ROLE_PRIORITY if CLASS_LIMITS.get(role, 0) > 0]

        for role in roles_to_fill:
            if len(squad['members']) >= squad_size:
                break
            if squad['class_counts'][role] >= CLASS_LIMITS.get(role, 99):
                continue

            best_player = None
            highest_score = -1

            # Find the best available player from the ELIGIBLE pool for this specific role
            for player in eligible_players:
                player_stats = player_stats_map.get(str(player['user_id']), {})
                # The player's sign-up subclass is also considered for suitability
                player_subclass = player.get('subclass_name')
                
                # If the role requires a specific subclass, check if the player has it
                if role in ["Officer", "Medic", "Support", "Anti-Tank", "etc."] and player_subclass != role:
                    # This logic can be refined, but for now, we assume a match is preferred
                    pass

                score = _calculate_suitability_score(player_stats, squad['squad_type'], role)
                
                if score > highest_score:
                    highest_score = score
                    best_player = player
            
            if best_player:
                squad['members'].append(best_player)
                squad['class_counts'][role] += 1
                eligible_players.remove(best_player)
        
        # Add any players from this pool who weren't placed to the final unplaced list
        unplaced_players.extend(eligible_players)

    # 4. CLEANUP: Assign all remaining players to a "Reserves" squad
    reserves_squad = {
        'name': "Reserves",
        'squad_type': "Reserves",
        'members': unplaced_players,
        'class_counts': defaultdict(int)
    }
    squads_to_fill.append(reserves_squad)

    # 5. FINALIZATION: Write the newly created squads and members to the database
    for squad_data in squads_to_fill:
        squad_id = await db.create_squad(event_id, squad_data['name'], squad_data['squad_type'])
        for member in squad_data['members']:
            # Find which role this member filled in the squad
            assigned_role = 'Unassigned'
            for m in squad_data['members']:
                if m['user_id'] == member['user_id']:
                    # This logic needs to be more robust to find the actual assigned role
                    # For now, we fall back to their signed-up role
                    assigned_role = member.get('subclass_name') or member.get('role_name', 'Unassigned')
                    break
            await db.add_squad_member(squad_id, member['user_id'], assigned_role)

    return await db.get_squads_with_members(event_id)
