import os
from config import CIYU_FILE


def check_code_exists(code):
    if not os.path.exists(CIYU_FILE):
        return None
    with open(CIYU_FILE, 'r', encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) > 1 and code in parts[1:]:
                return line.strip()
    return None


def parse_code(code):
    AB = code[:2]
    if len(code) > 2 and code[2].isdigit():
        C = code[2]
        if len(code) > 3:
            D = code[3]
            if len(code) > 4:
                E = code[4]
                return {"AB": AB, "C": C, "D": D, "E": E, "len": 5}
            else:
                return {"AB": AB, "C": C, "D": D, "E": None, "len": 4}
        else:
            return {"AB": AB, "C": C, "D": None, "E": None, "len": 3}
    else:
        return {"AB": AB, "C": None, "D": None, "E": None, "len": 2}


def generate_all_combinations(code1, code2):
    combos = []
    c1 = parse_code(code1)
    c2 = parse_code(code2)
    if c1["AB"] and c2["AB"]:
        combos.append(c1["AB"] + c2["AB"][0])
    combos.append(c1["AB"] + c2["AB"])
    if c2["C"]:
        combos.append(c1["AB"] + c2["AB"] + c2["C"])
    if c2["C"] and c2["D"]:
        combos.append(c1["AB"] + c2["AB"] + c2["C"] + c2["D"])
    if c2["C"] and c2["D"] and c2["E"]:
        combos.append(c1["AB"] + c2["AB"] + c2["C"] + c2["D"] + c2["E"])
    if c1["C"] and c2["C"]:
        combos.append(c1["AB"] + c1["C"] + c2["AB"] + c2["C"])
    if c1["C"] and c2["C"] and c2["D"]:
        combos.append(c1["AB"] + c1["C"] + c2["AB"] + c2["C"] + c2["D"])
    if c1["C"] and c2["C"] and c2["D"] and c2["E"]:
        combos.append(c1["AB"] + c1["C"] + c2["AB"] + c2["C"] + c2["D"] + c2["E"])
    if c1["C"] and c1["D"] and c2["C"]:
        combos.append(c1["AB"] + c1["C"] + c1["D"] + c2["AB"] + c2["C"])
    if c1["C"] and c1["D"] and c2["C"] and c2["D"]:
        combos.append(c1["AB"] + c1["C"] + c1["D"] + c2["AB"] + c2["C"] + c2["D"])
    if c1["C"] and c1["D"] and c2["C"] and c2["D"] and c2["E"]:
        combos.append(c1["AB"] + c1["C"] + c1["D"] + c2["AB"] + c2["C"] + c2["D"] + c2["E"])
    if c1["C"] and c1["D"] and c1["E"] and c2["C"]:
        combos.append(c1["AB"] + c1["C"] + c1["D"] + c1["E"] + c2["AB"] + c2["C"])
    if c1["C"] and c1["D"] and c1["E"] and c2["C"] and c2["D"]:
        combos.append(c1["AB"] + c1["C"] + c1["D"] + c1["E"] + c2["AB"] + c2["C"] + c2["D"])
    if c1["C"] and c1["D"] and c1["E"] and c2["C"] and c2["D"] and c2["E"]:
        combos.append(c1["AB"] + c1["C"] + c1["D"] + c1["E"] + c2["AB"] + c2["C"] + c2["D"] + c2["E"])
    combos = [c for c in combos if c]
    unique_combos = []
    for c in combos:
        if c not in unique_combos:
            unique_combos.append(c)
    return unique_combos


def generate_default_codes_for_word(word, selected_codes):
    n = len(word)
    codes_info = [parse_code(code) for code in selected_codes]
    ab_list = [info["AB"] for info in codes_info]
    initial_list = [ab[0] if ab else "" for ab in ab_list]
    defaults = ""
    if n == 3:
        code = ab_list[0] + ab_list[1] + initial_list[2]
    elif n == 4:
        code1 = ab_list[0] + ab_list[1] + ab_list[2] + initial_list[3]
        code2 = ''.join(initial_list)
        code = code1 + " " + code2
    elif n >= 5:
        code1 = ''.join(initial_list)
        code2 = ''.join(initial_list[:3]) + initial_list[-1]
        code = code1 + " " + code2
    defaults = code
    return defaults
