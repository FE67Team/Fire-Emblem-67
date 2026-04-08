from __future__ import annotations

import json
import os
from app.data.database.components import ComponentType
from app.data.database.database import DB
from app.data.database.skill_components import SkillComponent, SkillTags
from app.engine import engine, combat_calcs, item_funcs, item_system, skill_system, banner
from app.engine.game_state import game
from app.engine.objects.unit import UnitObject
from app.engine.movement import movement_funcs
from app.utilities import utils

LOVE_THRESHOLD = 5
LOVE_POINTS_PER_ADJACENCY = 1
LOVE_POINTS_PER_SUPPORT = 50
LOVE_POINTS_PER_STORY_EVENT = 100

PAIRABLE_MALES = [
    "Sain", "Kent", "Wil", "Dorcas", "Wallace", "Erk", "Eagler", "Eliwood",
    "Marcus", "Lowen", "Bartre", "Matthew", "Guy", "Dart", "Lucius", "Batta",
    "Erik", "Legault", "Heath", "Zealot", "Canas", "Hawkeye", "Geitz", "Fargus",
    "Uhai", "Lloyd", "Linus", "Renault", "Pent", "Hector"
]

PAIRABLE_FEMALES = [
    "Lyn", "Florina", "Serra", "Rebecca", "Priscilla", "Isadora", "Fiora",
    "Ninian", "Karla", "Louise", "Farina", "Nino", "Vaida", "Leila", "Juno"
]

PRE_PAIRED_COUPLES = [
    ("Pent", "Louise"),
]

def initialize_pre_paired_couples():
    for male, female in PRE_PAIRED_COUPLES:
        lovers_var = get_lovers_var(male, female)
        if not game.game_vars.get(lovers_var, False):
            game.game_vars[lovers_var] = True
            game.game_vars[get_love_var(male, female)] = 500

def get_student_parents_mapping():
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'game_data')
    filepath = os.path.join(data_dir, 'student_parents.json')
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
            return data.get('students', {})
    except Exception:
        return {}

def normalize_pair_key(unit1: str, unit2: str) -> str:
    if unit1 in PAIRABLE_FEMALES:
        return f"{unit1}_{unit2}"
    else:
        return f"{unit2}_{unit1}"

def get_love_var(unit1: str, unit2: str) -> str:
    key = normalize_pair_key(unit1, unit2)
    return f"Love_{key}"

def get_lovers_var(unit1: str, unit2: str) -> str:
    key = normalize_pair_key(unit1, unit2)
    return f"Lovers_{key}"

def units_adjacent(unit1: UnitObject, unit2: UnitObject) -> bool:
    if not unit1.position or not unit2.position:
        return False
    dx = abs(unit1.position[0] - unit2.position[0])
    dy = abs(unit1.position[1] - unit2.position[1])
    return dx <= 1 and dy <= 1 and (dx + dy) > 0

def is_pairable(unit: UnitObject) -> bool:
    if not unit:
        return False
    return unit.nid in PAIRABLE_MALES or unit.nid in PAIRABLE_FEMALES

def get_unit_by_nid(nid: str) -> UnitObject:
    for unit in game.get_all_units():
        if unit.nid == nid:
            return unit
    return None

def add_love_points(unit1_nid: str, unit2_nid: str, points: int, auto_tag: bool = True) -> int:
    love_var = get_love_var(unit1_nid, unit2_nid)
    current = game.game_vars.get(love_var, 0)
    new_points = min(current + points, 999)
    game.game_vars[love_var] = new_points
    print(f"[LOVE DEBUG] add_love_points: {unit1_nid} + {unit2_nid} = {new_points} (threshold: {LOVE_THRESHOLD})")
    
    if new_points >= LOVE_THRESHOLD:
        become_lovers(unit1_nid, unit2_nid, auto_tag)
    
    return new_points

def become_lovers(unit1_nid: str, unit2_nid: str, auto_tag: bool = True):
    lovers_var = get_lovers_var(unit1_nid, unit2_nid)
    if game.game_vars.get(lovers_var, False):
        return
    
    game.game_vars[lovers_var] = True
    
    parent1 = unit1_nid if unit1_nid in PAIRABLE_MALES else unit2_nid
    parent2 = unit2_nid if unit2_nid in PAIRABLE_FEMALES else unit1_nid
    
    print(f"[LOVE DEBUG] *** LOVERS! {parent1} and {parent2} ***")
    game.alerts.append(banner.Custom(f"{parent1} and {parent2} have become lovers!", 'Status'))
    
    if auto_tag:
        apply_parent_tags(unit1_nid, unit2_nid)

def apply_parent_tags(unit1_nid: str, unit2_nid: str):
    student_parents = get_student_parents_mapping()
    parent1 = unit1_nid if unit1_nid in PAIRABLE_MALES else unit2_nid
    parent2 = unit2_nid if unit2_nid in PAIRABLE_FEMALES else unit1_nid
    
    for student_nid, data in student_parents.items():
        if parent1 in data['parents'] or parent2 in data['parents']:
            student = get_unit_by_nid(student_nid)
            if student:
                tag1 = f"Parent_{parent1}"
                tag2 = f"Parent_{parent2}"
                if tag1 not in student.tags:
                    student.tags.append(tag1)
                if tag2 not in student.tags:
                    student.tags.append(tag2)

def check_love_adjacency(unit1_nid: str, unit2_nid: str) -> int:
    unit1 = get_unit_by_nid(unit1_nid)
    unit2 = get_unit_by_nid(unit2_nid)
    
    if not unit1 or not unit2:
        return 0
    
    if not unit1.position or not unit2.position:
        return 0
    
    if unit1.dead or unit2.dead:
        return 0
    
    if units_adjacent(unit1, unit2):
        return add_love_points(unit1_nid, unit2_nid, LOVE_POINTS_PER_ADJACENCY)
    
    return game.game_vars.get(get_love_var(unit1_nid, unit2_nid), 0)

def check_all_love_adjacencies() -> dict:
    results = {}
    all_units = list(game.get_all_units())
    
    for i, unit1 in enumerate(all_units):
        for unit2 in all_units[i+1:]:
            if not is_pairable(unit1) or not is_pairable(unit2):
                continue
            
            male = unit1.nid if unit1.nid in PAIRABLE_MALES else unit2.nid
            female = unit2.nid if unit2.nid in PAIRABLE_FEMALES else unit1.nid
            
            if male not in PAIRABLE_MALES or female not in PAIRABLE_FEMALES:
                continue
            
            love_var = get_love_var(male, female)
            lovers_var = get_lovers_var(male, female)
            
            if game.game_vars.get(lovers_var, False):
                continue
            
            if units_adjacent(unit1, unit2):
                new_points = add_love_points(male, female, LOVE_POINTS_PER_ADJACENCY)
                results[f"{male}_{female}"] = new_points
    
    return results

def get_love_points(unit1_nid: str, unit2_nid: str) -> int:
    return game.game_vars.get(get_love_var(unit1_nid, unit2_nid), 0)

def are_lovers(unit1_nid: str, unit2_nid: str) -> bool:
    return game.game_vars.get(get_lovers_var(unit1_nid, unit2_nid), False)

def reset_love_system():
    keys_to_remove = [k for k in game.game_vars.keys() if k.startswith('Love_') or k.startswith('Lovers_')]
    for key in keys_to_remove:
        del game.game_vars[key]

class LovePointsAdjacency(SkillComponent):
    nid = 'love_points_adjacency'
    desc = 'Gives love points when adjacent to pairable opposite-gender unit. Used for adjacency-based love point system.'
    tag = SkillTags.CUSTOM
    expose = ComponentType.Int
    value = 1
    
    def on_endstep_unconditional(self, actions, playback, unit):
        print(f"[LOVE DEBUG] on_endstep called for {unit.nid}")
        if not unit.position:
            return
        if unit.nid not in PAIRABLE_MALES and unit.nid not in PAIRABLE_FEMALES:
            print(f"[LOVE DEBUG] {unit.nid} is not pairable")
            return
        
        opposite_gender = PAIRABLE_FEMALES if unit.nid in PAIRABLE_MALES else PAIRABLE_MALES
        
        for other in game.get_all_units():
            if other.nid not in opposite_gender:
                continue
            if not other.position:
                continue
            if other.dead:
                continue
            
            male = unit.nid if unit.nid in PAIRABLE_MALES else other.nid
            female = other.nid if other.nid in PAIRABLE_FEMALES else unit.nid
            
            if male not in PAIRABLE_MALES or female not in PAIRABLE_FEMALES:
                continue
            
            love_var = get_love_var(male, female)
            lovers_var = get_lovers_var(male, female)
            
            if game.game_vars.get(lovers_var, False):
                continue
            
            if units_adjacent(unit, other):
                print(f"[LOVE DEBUG] {male} and {female} are adjacent!")
                new_points = add_love_points(male, female, self.value)

class LovePointsSupport(SkillComponent):
    nid = 'love_points_support'
    desc = 'Gives love points when support rank increases. Tracks romantic potential separately from regular supports.'
    tag = SkillTags.CUSTOM
    expose = ComponentType.Int
    value = 50
    
    @classmethod
    def on_support_gain(cls, unit1: UnitObject, unit2: UnitObject, rank: str) -> None:
        male = unit1.nid if unit1.nid in PAIRABLE_MALES else unit2.nid
        female = unit2.nid if unit2.nid in PAIRABLE_FEMALES else unit1.nid
        
        if male not in PAIRABLE_MALES or female not in PAIRABLE_FEMALES:
            return
        
        add_love_points(male, female, cls.value)

def check_broad_focus(unit: UnitObject, limit: int = 3, tag: str = "") -> int:
    """
    Counts the number of units with a specific tag within a specified distance from a given unit.
    
    Args:
        unit (UnitObject): The unit whose surroundings are being checked.
        limit (int): The maximum distance within which units are considered. Defaults to 3.
        tag (str): The tag to filter units by (e.g., 'Male', 'Female'). Defaults to None (all units).
    
    Returns:
        int: The count of matching units within the specified distance from the given unit.
    """
    from app.utilities import utils
    counter = 0
    if unit.position:
        for other in game.get_all_units():
            if other.position and unit is not other:
                distance = utils.calculate_distance(unit.position, other.position)
                if distance <= limit:
                    if tag is None:
                        counter += 1
                    elif tag in other.tags:
                        counter += 1
    return counter

def register_custom_functions():
    """Register custom functions to the game's query engine for use in skill conditions."""
    if hasattr(game, 'query_engine') and hasattr(game.query_engine, 'func_dict'):
        game.query_engine.func_dict['check_broad_focus'] = check_broad_focus
