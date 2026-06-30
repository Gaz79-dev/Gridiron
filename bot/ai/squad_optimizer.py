import re
from collections import defaultdict
from typing import List, Dict, Optional, Any
import json

# Use absolute imports from the 'bot' package root
from bot.utils.database import Database, RsvpStatus
from bot.api.models import SquadBuildRequest

# --- Constants & Configuration ---
from bot.game_systems.hll import CLASS_LIMITS, ROLE_PRIORITY, SPA_ROLES_TO_FILL, SQUAD_SIZE_BY_TYPE


# --- AI Helper Functions ---

def _calculate_suitability_score(player_stats: Dict[str, Any], target_squad_type: str, target_role: str) -> float:
    """
    Calculates a player's suitability for a specific role and squad type.
    """
    # Safety Check: Ensure player_stats is actually a dictionary
    if not isinstance(player_stats, dict):
        return 0.0

    # Weights for the scoring algorithm
    # Note: SIGNUP_MATCH_WEIGHT is less critical now due to strict filtering, 
    # but kept for logical consistency.
    SIGNUP_MATCH_WEIGHT = 0.50  
    RATING_WEIGHT = 0.30        
    ROLE_AFFINITY_WEIGHT = 0.15 
    SQUAD_AFFINITY_WEIGHT = 0.05

    # 1. Signup Match Score
    signup_role = player_stats.get('subclass_name') or ''
    signup_match = 1.0 if signup_role == target_role else 0.0

    # 2. Rating Score
    rating = player_stats.get('rating')
    if not isinstance(rating, (int, float)):
        rating = 50

    # 3. Affinity Scores (Learning from history)
    affinities_raw = player_stats.get('role_affinities')
    affinities = {}
    
    # Robust parsing logic
    if isinstance(affinities_raw, str):
        try:
            parsed = json.loads(affinities_raw)
            if isinstance(parsed, dict):
                affinities = parsed
        except (json.JSONDecodeError, TypeError):
            affinities = {} 
    elif isinstance(affinities_raw, dict):
        affinities = affinities_raw
        
    if not isinstance(affinities, dict):
        affinities = {}

    squad_counts = affinities.get('squad_types')
    if not isinstance(squad_counts, dict): squad_counts = {}
    
    role_counts = affinities.get('roles')
    if not isinstance(role_counts, dict): role_counts = {}

    total_squad_placements = sum(squad_counts.values()) if squad_counts else 0
    squad_affinity = (squad_counts.get(target_squad_type, 0) / total_squad_placements) if total_squad_placements > 0 else 0

    total_role_placements = sum(role_counts.values()) if role_counts else 0
    role_affinity = (role_counts.get(target_role, 0) / total_role_placements) if total_role_placements > 0 else 0

    # Composite Score Calculation
    suitability_score = (
        (signup_match * 100 * SIGNUP_MATCH_WEIGHT) +
        (rating * RATING_WEIGHT) +
        (role_affinity * 100 * ROLE_AFFINITY_WEIGHT) +
        (squad_affinity * 100 * SQUAD_AFFINITY_WEIGHT)
    )
    
    return suitability_score

def get_squad_iteration(base_name: str, existing_names: List[str], convention: str, group_index: int) -> str:
    """Gets the next available name for a squad, avoiding collisions."""
    highest_count = 0
    for name in existing_names:
        if name.startswith(base_name):
            if convention == 'numeric':
                match = re.search(rf'\({group_index}\.(\d+)\)', name)
                if match:
                    highest_count = max(highest_count, int(match.group(1)))
            elif convention == 'alpha':
                match = re.search(r' ([A-Z])$', name)
                if match:
                    num = ord(match.group(1)) - ord('A') + 1
                    highest_count = max(highest_count, num)

    next_count = highest_count + 1
    
    if convention == 'numeric':
        return f"{base_name} ({group_index}.{next_count})"
    elif convention == 'alpha':
        iteration_char = chr(ord('A') + next_count - 1)
        return f"{base_name} {iteration_char}"
    else: # 'none'
        return base_name

async def run_ai_draft(db: Database, event_id: int, request: SquadBuildRequest) -> List[Dict]:
    """
    Incrementally rebuilds squads using a reconciliation approach that respects template order,
    player RSVP pools, and HLL class limits.
    """
    # 1. GET CURRENT & DESIRED STATE
    current_squads_list = await db.get_squads_with_members(event_id)
    current_squads_map = {s['name']: s for s in current_squads_list}
    
    template = await db.get_squad_template_by_id(request.template_id)
    if not template:
        raise ValueError("Squad template not found.")

    # 2. CALCULATE THE DESIRED SQUAD LAYOUT IN THE CORRECT ORDER
    desired_squad_names = []
    squad_definitions_map = {}
    numeric_group_index = 1
    
    for definition in template['definitions']:
        base_name = definition['squad_name']
        convention = definition['naming_convention']
        group_index_for_naming = numeric_group_index if convention == 'numeric' else 0
        squad_definitions_map[base_name] = definition
        
        existing_names_for_type = [name for name in desired_squad_names if name.startswith(base_name)]
        for _ in range(request.squad_counts.get(base_name, 0)):
            new_name = get_squad_iteration(base_name, existing_names_for_type, convention, group_index_for_naming)
            desired_squad_names.append(new_name)
            existing_names_for_type.append(new_name)
        
        if convention == 'numeric':
            numeric_group_index += 1
            
    # 3. RECONCILE: Fetch ALL accepted players first
    new_squads_map = {}
    
    all_accepted_signups = await db.get_signups_for_roster_page(event_id)
    available_players_map = {
        int(p['user_id']): p for p in all_accepted_signups if p['rsvp_status'] == RsvpStatus.ACCEPTED
    }

    # Preserve players who are already in squads that will continue to exist
    for squad_name, squad_data in current_squads_map.items():
        if squad_name in desired_squad_names:
            new_squads_map[squad_name] = squad_data['members']
            # Remove these preserved players from the available pool
            for member in squad_data['members']:
                available_players_map.pop(int(member['user_id']), None)

    # The remaining players are now correctly available for placement
    available_player_pools = defaultdict(list)
    for player_data in available_players_map.values():
        if isinstance(player_data, dict):
            # Use role_name (e.g., "Infantry") as the pool key
            pool_key = player_data.get('role_name') or "Unassigned"
            available_player_pools[pool_key].append(player_data)
        
    # 4. FILL NEWLY CREATED SQUADS using a squad-centric approach
    for squad_name in desired_squad_names:
        if squad_name not in new_squads_map:
            base_name = re.split(r' \(\d', squad_name)[0].strip()
            definition = squad_definitions_map.get(base_name)
            if not definition: continue

            new_squad_members = []
            class_counts = defaultdict(int)
            squad_size = SQUAD_SIZE_BY_TYPE.get(definition['squad_type'], 6)
            
            pool_key = definition.get('source_rsvp_pool', 'Unassigned')
            eligible_players = available_player_pools[pool_key]
            
            roles_to_fill = ROLE_PRIORITY
            if definition['squad_type'] == "Armour":
                roles_to_fill = ["Tank Commander", "Crewman"]
            elif definition['squad_type'] == "SPA":
                roles_to_fill = SPA_ROLES_TO_FILL.copy()
            elif definition['squad_type'] == "Recon":
                roles_to_fill = ["Spotter", "Sniper"]
            
            # Fill the squad role-by-role
            for role in roles_to_fill:
                if len(new_squad_members) >= squad_size: break
                
                if class_counts[role] >= CLASS_LIMITS.get(role, 99): continue

                best_player = None
                highest_score = -1
                
                # Iterate over a copy to allow safe removal
                for player in eligible_players[:]:
                    if isinstance(player, dict):
                        # --- STRICT FILTER START ---
                        # Only consider players who signed up SPECIFICALLY for this class.
                        # e.g., only "Anti-Tank" signups can fill the "Anti-Tank" slot.
                        player_signup_role = player.get('subclass_name')
                        if player_signup_role != role:
                            continue
                        # --- STRICT FILTER END ---

                        score = _calculate_suitability_score(player, definition['squad_type'], role)
                        if score > highest_score:
                            highest_score = score
                            best_player = player
                
                if best_player:
                    best_player['assigned_role_name'] = role
                    new_squad_members.append(best_player)
                    class_counts[role] += 1
                    if best_player in eligible_players:
                        eligible_players.remove(best_player)
            
            new_squads_map[squad_name] = new_squad_members

    # 5. COMMIT CHANGES TO DATABASE
    await db.delete_squads_for_event(event_id)
    
    for squad_name in desired_squad_names:
        base_name = re.split(r' \(\d', squad_name)[0].strip()
        definition = squad_definitions_map.get(base_name)
        if not definition: continue
        
        squad_id = await db.create_squad(event_id, squad_name, definition['squad_type'])
        for member in new_squads_map.get(squad_name, []):
            if isinstance(member, dict):
                assigned_role = member.get('assigned_role_name') or member.get('subclass_name') or 'Unassigned'
                await db.add_squad_member(squad_id, int(member['user_id']), assigned_role)

    # Add any leftover players to a new Reserves squad
    reserves_id = await db.create_squad(event_id, "Reserves", "Reserves")
    remaining_players = [p for pool in available_player_pools.values() for p in pool]
    for player in remaining_players:
        if isinstance(player, dict):
            assigned_role = player.get('subclass_name') or player.get('role_name') or 'Unassigned'
            await db.add_squad_member(reserves_id, int(player['user_id']), assigned_role)

    return await db.get_squads_with_members(event_id)
