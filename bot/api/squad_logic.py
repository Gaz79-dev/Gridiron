from collections import defaultdict
from typing import List, Dict
from bot.utils.database import Database, RsvpStatus

CLASS_LIMITS = {
    "Officer": 1, "Anti-Tank": 1, "Machine Gunner": 1, "Automatic Rifleman": 1,
    "Spotter": 1, "Sniper": 1, "Tank Commander": 1, "Medic": 1, "Support": 1, "Engineer": 1
}

def get_squad_iteration(squad_name: str, counts: Dict, convention: str, group_index: int) -> str:
    """Gets the next iteration for a squad name based on the convention."""
    counts[squad_name] = counts.get(squad_name, 0) + 1
    count = counts[squad_name]
    
    if convention == 'numeric':
        return f"{squad_name} ({group_index}.{count})"
    elif convention == 'alpha':
        iteration_char = chr(ord('A') + count - 1) if count <= 26 else f"Z{count - 26}"
        return f"{squad_name} {iteration_char}"
    else: # 'none' or any other value
        return squad_name

async def run_web_draft(db: Database, event_id: int, request_data) -> List[Dict]:
    """The core logic for drafting players into squads based on a dynamic template."""
    await db.delete_squads_for_event(event_id)
    signups = await db.get_signups_for_event(event_id)
    
    player_pools = defaultdict(list)
    for signup in signups:
        if signup['rsvp_status'] == RsvpStatus.ACCEPTED:
            pool_key = signup['role_name'] or "Unassigned"
            player_pools[pool_key].append(dict(signup))

    template = await db.get_squad_template_by_id(request_data.template_id)
    if not template:
        raise ValueError("Squad template not found.")
    
    squad_counts, squads_to_fill = {}, []
    
    if request_data.squad_counts.get("Commander", 0) > 0:
        commander_squad_id = await db.create_squad(event_id, "Commander", "Command")
        squads_to_fill.append({
            'id': commander_squad_id, 'squad_name': 'Commander', 'squad_type': 'Command',
            'class_counts': defaultdict(int), 'source_rsvp_pool': 'Commander'
        })

    # Use enumerate to get the group index for sequential numeric naming
    for i, definition in enumerate(template['definitions'], 1):
        squad_name = definition['squad_name']
        count = request_data.squad_counts.get(squad_name, 0)
        
        for _ in range(count):
            full_squad_name = get_squad_iteration(squad_name, squad_counts, definition['naming_convention'], i)
            s_id = await db.create_squad(event_id, full_squad_name, definition['squad_type'])
            squads_to_fill.append({
                'id': s_id, 'squad_name': squad_name, 'squad_type': definition['squad_type'],
                'class_counts': defaultdict(int), 'source_rsvp_pool': definition['source_rsvp_pool']
            })

    for squad in squads_to_fill:
        player_pool = player_pools.get(squad['source_rsvp_pool'], [])
        
        squad_size = 1 if squad['squad_type'] == "Command" else \
                     3 if squad['squad_type'] == "Armour" else \
                     2 if squad['squad_type'] in ["Recon", "Artillery"] else 6

        subclass_priority = ["Officer", "Medic", "Support", "Anti-Tank", "Machine Gunner", "Spotter", "Tank Commander", "Automatic Rifleman", "Engineer", "Assault", "Rifleman", "Crewman", "Sniper"]
        player_pool.sort(key=lambda p: subclass_priority.index(p['subclass_name']) if p.get('subclass_name') in subclass_priority else 99)

        temp_unplaced_pool = []
        member_count = 0
        
        while member_count < squad_size and player_pool:
            player = player_pool.pop(0)
            player_class = player.get('subclass_name')
            
            if not player_class:
                temp_unplaced_pool.append(player)
                continue

            limit = CLASS_LIMITS.get(player_class, 99)

            if squad['class_counts'][player_class] < limit:
                await db.add_squad_member(squad['id'], player['user_id'], player_class)
                squad['class_counts'][player_class] += 1
                member_count += 1
            else:
                temp_unplaced_pool.append(player)
        
        player_pools[squad['source_rsvp_pool']] = temp_unplaced_pool + player_pool

    reserves_squad_id = await db.create_squad(event_id, "Reserves", "Reserves")
    for pool_key in player_pools:
        for player in player_pools[pool_key]:
            assigned_role = player.get('subclass_name') or player.get('role_name', 'Unassigned')
            await db.add_squad_member(reserves_squad_id, player['user_id'], assigned_role)
        
    return await db.get_squads_with_members(event_id)
