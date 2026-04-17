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

LOVE_THRESHOLD = 25
LOVER_BONUS_SKILL_NID = 'Lovers_Bond'
LOVER_BONUS_RANGE = 3
LOVER_BONUS_HIT = 10
LOVER_BONUS_AVOID = 10

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

_love_pairs_config = None

def get_love_pairs_config():
    global _love_pairs_config
    if _love_pairs_config is not None:
        return _love_pairs_config
    
    if DB.current_proj_dir:
        filepath = os.path.join(DB.current_proj_dir, 'game_data', 'love_pairs_config.json')
    else:
        current_file = os.path.abspath(__file__)
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(current_file)))
        filepath = os.path.join(base_dir, 'game_data', 'love_pairs_config.json')
    
    try:
        with open(filepath, 'r') as f:
            _love_pairs_config = json.load(f)
            print(f"[LOVE] Config loaded successfully from: {filepath}")
            return _love_pairs_config
    except Exception as e:
        print(f"[LOVE] Warning: Could not load love_pairs_config.json: {e}")
        print(f"[LOVE] Tried path: {filepath}")
        _love_pairs_config = {"default_rate": 1, "pairs": {}}
        return _love_pairs_config
    
    current_file = os.path.abspath(__file__)
    project_dir = os.path.dirname(os.path.dirname(os.path.dirname(current_file)))
    filepath = os.path.join(project_dir, 'game_data', 'love_pairs_config.json')
    try:
        with open(filepath, 'r') as f:
            _love_pairs_config = json.load(f)
            return _love_pairs_config
    except Exception as e:
        print(f"[LOVE] Warning: Could not load love_pairs_config.json: {e}")
        print(f"[LOVE] Tried path: {filepath}")
        _love_pairs_config = {"default_rate": 1, "pairs": {}}
        return _love_pairs_config

def get_love_rate(unit1_nid: str, unit2_nid: str) -> int:
    config = get_love_pairs_config()
    key = normalize_pair_key(unit1_nid, unit2_nid)
    return config.get("pairs", {}).get(key, config.get("default_rate", 1))

def initialize_pre_paired_couples():
    for male, female in PRE_PAIRED_COUPLES:
        lovers_var = get_lovers_var(male, female)
        if not game.game_vars.get(lovers_var, False):
            game.game_vars[lovers_var] = True
            game.game_vars[get_love_var(male, female)] = 500
            apply_lover_bonus(male, female)

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

def get_lover_nid_var(unit_nid: str) -> str:
    return f" Lover_{unit_nid}"

def units_within_range(unit1: UnitObject, unit2: UnitObject, range: int) -> bool:
    if not unit1.position or not unit2.position:
        return False
    distance = utils.calculate_distance(unit1.position, unit2.position)
    return distance <= range

def is_pairable(unit: UnitObject) -> bool:
    if not unit:
        return False
    return unit.nid in PAIRABLE_MALES or unit.nid in PAIRABLE_FEMALES

def get_unit_by_nid(nid: str) -> UnitObject:
    for unit in game.get_all_units():
        if unit.nid == nid:
            return unit
    return None

def has_current_lover(unit_nid: str) -> bool:
    lover_var = get_lover_nid_var(unit_nid)
    return game.game_vars.get(lover_var, None) is not None

def get_current_lover(unit_nid: str) -> str:
    lover_var = get_lover_nid_var(unit_nid)
    return game.game_vars.get(lover_var, None)

def add_love_points(unit1_nid: str, unit2_nid: str, points: int, auto_tag: bool = True) -> int:
    male = unit1_nid if unit1_nid in PAIRABLE_MALES else unit2_nid
    female = unit2_nid if unit2_nid in PAIRABLE_FEMALES else unit1_nid
    
    if has_current_lover(male) and get_current_lover(male) != female:
        print(f"[LOVE] {male} already has a lover ({get_current_lover(male)}), cannot pair with {female}")
        return game.game_vars.get(get_love_var(unit1_nid, unit2_nid), 0)
    if has_current_lover(female) and get_current_lover(female) != male:
        print(f"[LOVE] {female} already has a lover ({get_current_lover(female)}), cannot pair with {male}")
        return game.game_vars.get(get_love_var(unit1_nid, unit2_nid), 0)
    
    love_var = get_love_var(unit1_nid, unit2_nid)
    current = game.game_vars.get(love_var, 0)
    new_points = min(current + points, 999)
    game.game_vars[love_var] = new_points
    print(f"[LOVE] +{points} points: {male} + {female} = {new_points}/{LOVE_THRESHOLD}")
    
    if new_points >= LOVE_THRESHOLD:
        become_lovers(unit1_nid, unit2_nid, auto_tag)
    
    return new_points

def become_lovers(unit1_nid: str, unit2_nid: str, auto_tag: bool = True):
    lovers_var = get_lovers_var(unit1_nid, unit2_nid)
    if game.game_vars.get(lovers_var, False):
        return
    
    male = unit1_nid if unit1_nid in PAIRABLE_MALES else unit2_nid
    female = unit2_nid if unit2_nid in PAIRABLE_FEMALES else unit1_nid
    
    if has_current_lover(male) and get_current_lover(male) != female:
        return
    if has_current_lover(female) and get_current_lover(female) != male:
        return
    
    game.game_vars[lovers_var] = True
    
    lover_nid_var_m = get_lover_nid_var(male)
    lover_nid_var_f = get_lover_nid_var(female)
    game.game_vars[lover_nid_var_m] = female
    game.game_vars[lover_nid_var_f] = male
    
    print(f"[LOVE] *** {male} and {female} ARE NOW LOVERS! ***")
    game.alerts.append(banner.Custom(f"{male} and {female} have become lovers!", 'Status'))
    
    if auto_tag:
        apply_parent_tags(unit1_nid, unit2_nid)
    
    apply_lover_bonus(male, female)

def apply_lover_bonus(male: str, female: str):
    from app.engine import item_funcs
    
    male_unit = get_unit_by_nid(male)
    female_unit = get_unit_by_nid(female)
    
    # Give Lovers_Bond skill to both units
    if male_unit and 'Lovers_Bond' not in [s.nid for s in male_unit.skills]:
        new_skill = item_funcs.create_skill(male_unit, LOVER_BONUS_SKILL_NID)
        if new_skill:
            male_unit.skills.append(new_skill)
            print(f"[LOVE] Added Lovers_Bond to {male}")
    
    if female_unit and 'Lovers_Bond' not in [s.nid for s in female_unit.skills]:
        new_skill = item_funcs.create_skill(female_unit, LOVER_BONUS_SKILL_NID)
        if new_skill:
            female_unit.skills.append(new_skill)
            print(f"[LOVE] Added Lovers_Bond to {female}")

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

def get_love_points(unit1_nid: str, unit2_nid: str) -> int:
    return game.game_vars.get(get_love_var(unit1_nid, unit2_nid), 0)

def are_lovers(unit1_nid: str, unit2_nid: str) -> bool:
    return game.game_vars.get(get_lovers_var(unit1_nid, unit2_nid), False)

def reset_love_system():
    keys_to_remove = [k for k in game.game_vars.keys() if k.startswith('Love_') or k.startswith('Lovers_') or k.startswith(' Lover_')]
    for key in keys_to_remove:
        del game.game_vars[key]

def give_love_points_from_talk(unit1_nid: str, unit2_nid: str, points: int):
    print(f"[LOVE] give_love_points_from_talk called: {unit1_nid} + {unit2_nid} = {points}")
    male = unit1_nid if unit1_nid in PAIRABLE_MALES else unit2_nid
    female = unit2_nid if unit2_nid in PAIRABLE_FEMALES else unit1_nid
    
    print(f"[LOVE] Detected: male={male} (in males: {male in PAIRABLE_MALES}), female={female} (in females: {female in PAIRABLE_FEMALES})")
    
    if male in PAIRABLE_MALES and female in PAIRABLE_FEMALES:
        print(f"[LOVE] Valid pair, calling add_love_points...")
        add_love_points(male, female, points)
        return True
    print(f"[LOVE] Invalid pair - not adding points")
    return False

class LovePointsAdjacency(SkillComponent):
    nid = 'love_points_adjacency'
    desc = 'Gives love points when adjacent to pairable opposite-gender unit. Used for adjacency-based love point system.'
    tag = SkillTags.CUSTOM
    expose = ComponentType.Int
    value = 1
    
    def on_endstep_unconditional(self, actions, playback, unit):
        print(f"[LOVE] on_endstep called for unit: {unit.nid}")
        if not unit.position:
            print(f"[LOVE] {unit.nid} has no position")
            return
        if unit.nid not in PAIRABLE_MALES and unit.nid not in PAIRABLE_FEMALES:
            print(f"[LOVE] {unit.nid} not in pairable units")
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
            
            if units_within_range(unit, other, 1):
                print(f"[LOVE] {male} and {female} are adjacent, checking love rate...")
                rate = get_love_rate(male, female)
                print(f"[LOVE] Love rate for {male}_{female}: {rate}")
                add_love_points(male, female, rate)

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

class LoversBondSkill(SkillComponent):
    nid = 'lovers_bond'
    desc = f'Gives +{LOVER_BONUS_HIT} Hit and +{LOVER_BONUS_AVOID} Avoid when lover is within {LOVER_BONUS_RANGE} tiles.'
    tag = SkillTags.COMBAT
    
    def on_upkeep(self, actions, playback, unit):
        from app.engine import action, item_funcs
        
        lover_var = get_lover_nid_var(unit.nid)
        lover_nid = game.game_vars.get(lover_var)
        if not lover_nid:
            return
        
        lover_unit = get_unit_by_nid(lover_nid)
        if not lover_unit:
            return
        
        if not lover_unit.position or lover_unit.dead:
            return
        
        if units_within_range(unit, lover_unit, LOVER_BONUS_RANGE):
            # Add the child skill to self if not present
            child_skill_nid = 'Lovers_Bond_Child'
            if child_skill_nid not in [s.nid for s in unit.skills]:
                child_skill = item_funcs.create_skill(unit, child_skill_nid)
                if child_skill:
                    actions.append(action.AddSkill(unit, child_skill))
            
            # Add the child skill to lover if not present
            if child_skill_nid not in [s.nid for s in lover_unit.skills]:
                child_skill = item_funcs.create_skill(lover_unit, child_skill_nid)
                if child_skill:
                    actions.append(action.AddSkill(lover_unit, child_skill))
    
    def on_endstep_unconditional(self, actions, playback, unit):
        # Remove child skill at end of turn
        child_skill_nid = 'Lovers_Bond_Child'
        for s in unit.skills:
            if s.nid == child_skill_nid:
                from app.engine import action
                actions.append(action.RemoveSkill(unit, s))
                break

class LovePointsInitializer(SkillComponent):
    nid = 'love_points_initializer'
    desc = 'Initializes love points system on game load'
    tag = SkillTags.CUSTOM
    
    def on_start(self, actions, playback, unit):
        from app.engine.game_state import game as current_game
        try:
            current_game.query_engine.func_dict['give_love_points_from_talk'] = give_love_points_from_talk
            print("[LOVE] Love points function registered via skill")
        except Exception as e:
            print(f"[LOVE] Failed to register: {e}")

def check_broad_focus(unit: UnitObject, limit: int = 3, tag: str = "") -> int:
    counter = 0
    if unit.position:
        for other in game.get_all_units():
            if other.position and unit is not other:
                distance = utils.calculate_distance(unit.position, other.position)
                if distance <= limit:
                    if tag is None or tag == "":
                        counter += 1
                    elif tag in other.tags:
                        counter += 1
    return counter

def register_custom_functions():
    try:
        if hasattr(game, 'query_engine') and hasattr(game.query_engine, 'func_dict'):
            game.query_engine.func_dict['check_broad_focus'] = check_broad_focus
            game.query_engine.func_dict['give_love_points_from_talk'] = give_love_points_from_talk
            print("[LOVE] Registered custom functions to query_engine")
    except Exception as e:
        print(f"[LOVE] Could not register functions: {e}")