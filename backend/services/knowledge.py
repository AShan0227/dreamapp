"""Dream Knowledge Engine — L0/L1 lookup and context injection.

Loads 5 knowledge bases:
- symbols.json: 55 dream symbols with cross-cultural interpretations
- archetypes.json: 18 Jungian archetypes + dream-archetype mappings
- narratives.json: 14 narrative archetypes + Campbell + Booker
- tcm_dreams.json: TCM organ-dream mapping + Ayurveda
- film_techniques.json: Cinematic technique taxonomy from 10 dream films
"""

import json
from pathlib import Path

KNOWLEDGE_DIR = Path(__file__).parent.parent / "knowledge"

# Knowledge stores
_symbols: list[dict] = []
_archetypes: list[dict] = []
_archetype_patterns: list[dict] = []
_narratives: list[dict] = []
_tcm_organs: list[dict] = []
_film_techniques: dict = {}
_prompt_guide: dict = {}  # Style presets + emotion-to-visual mappings


def _load_json(filename: str) -> dict | list:
    path = KNOWLEDGE_DIR / filename
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _load():
    global _symbols, _archetypes, _archetype_patterns, _narratives, _tcm_organs, _film_techniques, _prompt_guide

    # Symbols
    data = _load_json("symbols.json")
    if isinstance(data, list):
        _symbols = data
    elif isinstance(data, dict):
        _symbols = data.get("symbols", [])

    # Archetypes
    data = _load_json("archetypes.json")
    if isinstance(data, dict):
        _archetypes = data.get("archetypes", [])
        patterns = data.get("dream_archetype_patterns", {})
        if isinstance(patterns, dict):
            _archetype_patterns = patterns.get("patterns", patterns.get("mappings", []))
            if not isinstance(_archetype_patterns, list):
                _archetype_patterns = []
        elif isinstance(patterns, list):
            _archetype_patterns = patterns

    # Narratives
    data = _load_json("narratives.json")
    if isinstance(data, dict):
        _narratives = data.get("narrative_archetypes", data.get("archetypes", data.get("narratives", [])))
        if not isinstance(_narratives, list):
            _narratives = []

    # TCM
    data = _load_json("tcm_dreams.json")
    if isinstance(data, dict):
        _tcm_organs = data.get("five_organ_systems", data.get("organ_systems", data.get("five_organs", [])))

    # Film techniques
    _film_techniques = _load_json("film_techniques.json")
    if isinstance(_film_techniques, list):
        _film_techniques = {}

    # Prompt guide
    _prompt_guide = _load_json("prompt_guide.json")
    if isinstance(_prompt_guide, list):
        _prompt_guide = {}


_load()


# --- Chinese keyword expansions ---
_CN_KEYWORDS: dict[str, list[str]] = {
    "水": ["水", "海", "河", "湖", "游泳", "溺水", "浪", "洪水", "雨", "泳池", "水下", "海底", "潜水"],
    "蛇": ["蛇", "蟒", "毒蛇"],
    "飞翔": ["飞", "飘", "飞翔", "飞行", "翅膀", "悬浮", "腾空"],
    "坠落": ["掉", "坠", "落", "摔", "跌", "掉下", "坠落", "跌落", "摔下"],
    "被追赶": ["追", "追赶", "逃跑", "被追", "追杀", "逃", "跑不动"],
    "掉牙": ["牙", "掉牙", "牙齿", "牙掉"],
    "死亡": ["死", "死亡", "去世", "葬礼", "棺材"],
    "裸体 / 穿着不当": ["裸", "没穿", "光着", "裸体"],
    "考试 / 上学": ["考试", "考", "学校", "上学", "课堂", "迟到"],
    "蜘蛛": ["蜘蛛"],
    "鸟": ["鸟", "飞鸟"],
    "猫": ["猫"],
    "狗": ["狗"],
    "鱼": ["鱼"],
    "龙": ["龙"],
    "地震": ["地震", "震"],
    "火": ["火", "着火", "火灾", "燃烧"],
    "桥": ["桥"],
    "山": ["山", "爬山", "山顶"],
    "门": ["门", "大门", "门口"],
    "楼": ["楼", "大楼", "高楼", "建筑", "房子", "房间", "屋"],
    "迷路": ["迷路", "迷", "找不到路", "走不出"],
    "婚礼": ["婚", "结婚", "婚礼"],
    "怀孕": ["怀孕", "孕", "生孩子"],
    "镜子": ["镜子", "镜", "照镜子"],
    "钱": ["钱", "金钱", "钞票"],
    "车": ["车", "开车", "汽车", "驾驶"],
    "飞机": ["飞机", "坐飞机"],
    "战争": ["战争", "打仗", "战斗"],
    "哭": ["哭", "流泪", "哭泣"],
}


# --- Symbol matching ---

def match_symbols(text: str) -> list[dict]:
    """Find dream symbols mentioned in text."""
    text_lower = text.lower()
    matched = []

    for symbol in _symbols:
        name = (symbol.get("name") or symbol.get("name_en") or "").lower()
        name_cn = (symbol.get("name_cn") or symbol.get("name_zh") or "").lower()
        variations = [v.lower() for v in (symbol.get("variations") or symbol.get("common_variations") or [])]

        hit = False
        for term in [name] + variations:
            if term and len(term) > 1 and term in text_lower:
                hit = True
                break

        if not hit and name_cn:
            cn_keywords = _CN_KEYWORDS.get(name_cn, [name_cn])
            for kw in cn_keywords:
                if kw and kw in text:
                    hit = True
                    break

        if hit:
            matched.append(symbol)

    return matched


# --- Archetype matching ---

# Map archetype scenarios to Chinese keywords for matching
_ARCHETYPE_CN_MAP: dict[str, list[str]] = {
    "being chased": ["追", "追赶", "逃", "被追"],
    "hidden rooms": ["房间", "密室", "暗门", "隐藏"],
    "wise stranger": ["老人", "智者", "陌生人指引"],
    "naked": ["裸", "没穿", "光着"],
    "flying": ["飞", "飘", "飞翔", "腾空"],
    "teeth": ["牙", "掉牙"],
    "death": ["死", "去世", "葬礼"],
    "water": ["水", "海", "河", "湖", "游泳"],
    "exam": ["考试", "考", "迟到"],
    "falling": ["掉", "坠", "摔", "跌"],
    "paralysis": ["动不了", "瘫痪", "不能动"],
    "child": ["孩子", "小孩", "婴儿", "儿童"],
    "wedding": ["婚", "结婚"],
    "house": ["楼", "房子", "房间", "建筑"],
    "snake": ["蛇"],
    "vehicle": ["车", "失控", "开车"],
    "disaster": ["地震", "洪水", "灾难"],
    "war": ["战争", "打仗"],
    "animal": ["动物", "狗", "猫", "鸟"],
    "prison": ["关", "困", "牢", "困住", "出不去"],
    "treasure": ["宝", "发现", "珍贵"],
    "bridge": ["桥"],
    "transform": ["变", "变成", "变形"],
    "mirror": ["镜子", "镜", "倒影"],
    "mountain": ["山", "爬山"],
    "stage": ["舞台", "表演", "演出"],
    "garden": ["花园", "花", "园"],
    "shadow": ["影子", "黑影", "阴影"],
    "cave": ["洞", "洞穴", "地下"],
}


def match_archetypes(text: str) -> list[dict]:
    """Match dream content to Jungian archetypes via dream-archetype patterns."""
    text_lower = text.lower()
    matched = []

    for pattern in _archetype_patterns:
        scenario = (pattern.get("dream_scenario") or "").lower()

        hit = False
        # English matching: check key words from scenario
        scenario_words = [w for w in scenario.split() if len(w) > 3]
        en_matches = sum(1 for w in scenario_words if w in text_lower)
        if en_matches >= 2:
            hit = True

        # Chinese matching: check CN keywords mapped to this scenario
        if not hit:
            for en_key, cn_words in _ARCHETYPE_CN_MAP.items():
                if en_key in scenario:
                    for cw in cn_words:
                        if cw in text:
                            hit = True
                            break
                    if hit:
                        break

        if hit:
            matched.append(pattern)

    return matched[:5]


# --- Narrative matching ---

# Chinese keywords for narrative archetypes
_NARRATIVE_CN_MAP: dict[str, list[str]] = {
    "hero": ["旅途", "冒险", "任务", "使命", "出发", "挑战"],
    "descent": ["往下", "地下", "地底", "深处", "下沉", "坠入", "地下室", "洞穴"],
    "chase": ["追", "逃", "跑", "追赶", "被追", "逃跑"],
    "metamorphosis": ["变成", "变形", "转变", "化身", "变成了"],
    "labyrinth": ["迷路", "找不到", "迷宫", "走不出", "绕来绕去"],
    "revelation": ["发现", "突然明白", "看到了", "原来是", "真相"],
    "loss": ["失去", "消失", "离开", "告别", "丢了", "再也"],
    "reunion": ["重逢", "找到了", "又见到", "团聚", "回来了"],
    "trial": ["考试", "考验", "测试", "比赛", "证明"],
    "flood": ["洪水", "淹没", "末日", "灾难", "海啸", "毁灭"],
    "garden": ["花园", "天堂", "美丽", "和平", "净土", "乐园"],
    "tower": ["困住", "关", "出不去", "牢", "被困", "封闭"],
    "crossing": ["桥", "门", "过去", "穿过", "对面", "彼岸"],
    "mirror": ["镜子", "倒影", "另一个自己", "分身", "双重"],
}


def match_narratives(text: str) -> list[dict]:
    """Match dream to narrative archetypes using detection keywords + Chinese."""
    text_lower = text.lower()
    matched = []

    for narrative in _narratives:
        keywords = narrative.get("detection_keywords", [])
        name = (narrative.get("name") or narrative.get("name_en") or "").lower()

        score = 0
        # English keywords
        for kw in keywords:
            if isinstance(kw, str) and kw.lower() in text_lower:
                score += 1

        # Chinese keywords
        for en_key, cn_words in _NARRATIVE_CN_MAP.items():
            if en_key in name:
                for cw in cn_words:
                    if cw in text:
                        score += 1
                break

        if score >= 2:
            matched.append((score, narrative))

    matched.sort(key=lambda x: x[0], reverse=True)
    return [n for _, n in matched[:3]]


# --- TCM matching ---

# Map TCM organs to Chinese dream keywords
_TCM_CN_KEYWORDS: dict[str, list[str]] = {
    "liver": ["怒", "愤怒", "吵架", "打架", "树", "森林", "绿", "风", "困住", "压抑"],
    "heart": ["火", "笑", "光", "太阳", "闪电", "燃烧", "噩梦", "惊醒", "恐惧", "心跳"],
    "spleen": ["吃", "食物", "饿", "房子", "泥", "沼泽", "担心", "焦虑", "思考", "黄"],
    "lung": ["哭", "悲伤", "白", "金属", "飞", "天空", "呼吸", "窒息", "秋", "衰败"],
    "kidney": ["水", "海", "河", "溺水", "黑暗", "深", "冷", "骨", "恐惧", "坠落", "冰"],
}

# English keywords too
_TCM_EN_KEYWORDS: dict[str, list[str]] = {
    "liver": ["anger", "fight", "tree", "forest", "wind", "trapped", "frustrated"],
    "heart": ["fire", "laugh", "light", "sun", "lightning", "burn", "nightmare", "fear"],
    "spleen": ["eat", "food", "hungry", "house", "mud", "swamp", "worry", "anxious"],
    "lung": ["cry", "grief", "white", "metal", "fly", "sky", "breath", "suffocate"],
    "kidney": ["water", "ocean", "river", "drown", "dark", "deep", "cold", "bone", "fall", "ice"],
}


def match_tcm(dream_script: dict) -> list[dict]:
    """Match dream content to TCM organ patterns."""
    all_text = json.dumps(dream_script, ensure_ascii=False)
    all_text_lower = all_text.lower()
    matched = []

    for organ in _tcm_organs:
        name_en = (organ.get("organ_en") or organ.get("name_en") or organ.get("name") or "").lower()

        hit = False
        # English keyword matching
        for key, keywords in _TCM_EN_KEYWORDS.items():
            if key in name_en:
                for kw in keywords:
                    if kw in all_text_lower:
                        hit = True
                        break
                break

        # Chinese keyword matching
        if not hit:
            for key, keywords in _TCM_CN_KEYWORDS.items():
                if key in name_en:
                    for kw in keywords:
                        if kw in all_text:
                            hit = True
                            break
                    break

        if hit:
            matched.append(organ)

    return matched[:3]


# --- Context builders ---

def get_interview_context(text: str) -> str:
    """Generate contextual knowledge for the interviewer."""
    sections = []

    # Symbols
    symbols = match_symbols(text)
    if symbols:
        lines = ["[KNOWLEDGE ENGINE — Detected dream symbols:]"]
        for sym in symbols[:5]:
            name = sym.get("name") or sym.get("name_en") or "?"
            freq = sym.get("frequency", "?")
            follow_ups = sym.get("follow_up_questions", [])
            psych = sym.get("psychological_interpretations", {})

            lines.append(f"\n**{name}** (frequency: {freq}/10)")
            if follow_ups:
                lines.append(f"  Suggested questions: {'; '.join(follow_ups[:3])}")
            jungian = psych.get("jungian", "")
            if jungian:
                lines.append(f"  Jungian: {jungian[:150]}")

        lines.append("\nUse this to inform your questions. Do NOT reveal analysis to user.")
        sections.append("\n".join(lines))

    # Archetype hints
    archetypes = match_archetypes(text)
    if archetypes:
        lines = ["[ARCHETYPE HINTS:]"]
        for pat in archetypes[:3]:
            archetype = pat.get("primary_archetype") or pat.get("archetype", "?")
            interp = pat.get("interpretation", "")
            lines.append(f"  {archetype}: {interp[:120]}")
        sections.append("\n".join(lines))

    return "\n\n".join(sections)


def get_interpretation_context(dream_script: dict) -> str:
    """Generate contextual knowledge for the interpreter."""
    all_text = json.dumps(dream_script, ensure_ascii=False)
    sections = []

    # Symbols
    symbols = match_symbols(all_text)
    if symbols:
        lines = ["[KNOWLEDGE ENGINE — Symbol reference:]"]
        for sym in symbols[:8]:
            name = sym.get("name") or sym.get("name_en") or "?"
            psych = sym.get("psychological_interpretations", {})
            cultural = sym.get("cultural_interpretations", {})

            lines.append(f"\n## {name}")
            for lens, interp in psych.items():
                if interp:
                    lines.append(f"  {lens}: {interp[:200]}")
            for culture, interp in cultural.items():
                if interp:
                    lines.append(f"  {culture}: {interp[:150]}")
        sections.append("\n".join(lines))

    # Archetypes
    archetypes = match_archetypes(all_text)
    if archetypes:
        lines = ["[JUNGIAN ARCHETYPES:]"]
        for pat in archetypes[:3]:
            archetype = pat.get("primary_archetype") or pat.get("archetype", "?")
            interp = pat.get("interpretation", "")
            questions = pat.get("key_questions", [])
            lines.append(f"\n**{archetype}**")
            lines.append(f"  {interp[:200]}")
            if questions:
                lines.append(f"  Key questions: {'; '.join(questions[:2])}")
        sections.append("\n".join(lines))

    # Narratives
    narratives = match_narratives(all_text)
    if narratives:
        lines = ["[NARRATIVE ARCHETYPES:]"]
        for nar in narratives[:2]:
            name = nar.get("name") or nar.get("name_en") or "?"
            significance = nar.get("psychological_significance", "")
            if isinstance(significance, dict):
                significance = significance.get("primary", "")
            lines.append(f"\n**{name}**")
            lines.append(f"  {str(significance)[:200]}")
        sections.append("\n".join(lines))

    # TCM
    tcm = match_tcm(dream_script)
    if tcm:
        lines = ["[TCM DREAM PERSPECTIVE:]"]
        for organ in tcm[:2]:
            organ_name = organ.get("organ_zh") or organ.get("organ_en") or organ.get("name") or "?"
            element = organ.get("element_zh") or organ.get("element_en") or organ.get("element", "")
            wellness = organ.get("wellness_recommendations", organ.get("recommendations", {}))
            lines.append(f"\n**{organ_name}** (element: {element})")
            if isinstance(wellness, dict):
                diet = wellness.get("dietary", wellness.get("diet", []))
                if isinstance(diet, list) and diet:
                    lines.append(f"  Diet: {', '.join(diet[:3])}")
        sections.append("\n".join(lines))

    return "\n\n".join(sections)


def get_director_context(dream_script: dict) -> str:
    """Generate film technique suggestions for the director."""
    scenes = dream_script.get("scenes", [])
    overall_emotion = dream_script.get("overall_emotion", "").lower()
    time_feel = dream_script.get("time_feel", "").lower()
    all_text = json.dumps(dream_script, ensure_ascii=False).lower()

    suggestions = ["[KNOWLEDGE ENGINE — Recommended cinematic techniques:]"]

    # Transitions
    transitions = _film_techniques.get("transitions", {})
    transition_map = {
        "elemental_threshold": ["water", "ocean", "sea", "river", "rain", "flood", "海", "水", "河", "雨"],
        "fluid_morph": ["transform", "change", "become", "morph", "shift", "变", "变成", "转变"],
        "environmental_collapse": ["collapse", "disappear", "fade", "crumble", "vanish", "消失", "崩塌"],
        "tunnel_passage": ["door", "tunnel", "corridor", "gate", "entrance", "门", "通道", "隧道"],
        "material_shift": ["cardboard", "paper", "handmade", "toy", "纸", "玩具"],
    }
    for tech_key, keywords in transition_map.items():
        if any(w in all_text for w in keywords):
            t = transitions.get(tech_key, {})
            if t:
                suggestions.append(f"  Transition: {t.get('name', '')} — {t.get('prompt_keywords', '')}")

    # Time techniques
    time_techs = _film_techniques.get("time_distortion", {})
    time_map = {
        "ultra_slow_motion": ["slow", "freeze", "慢", "静止", "frozen"],
        "repetition_variation": ["loop", "repeat", "again", "循环", "重复"],
        "parallel_speed": ["fast", "quick", "rapid", "快", "加速"],
        "non_chronological_drift": ["fragment", "jump", "skip", "碎片", "跳跃"],
        "temporal_collision": ["past", "future", "memory", "过去", "记忆", "未来"],
    }
    for tech_key, keywords in time_map.items():
        if any(w in all_text or w in time_feel for w in keywords):
            t = time_techs.get(tech_key, {})
            if t:
                suggestions.append(f"  Time: {t.get('name', '')} — {t.get('prompt_keywords', '')}")

    # Camera based on emotion
    camera = _film_techniques.get("camera_grammar", {})
    if any(w in overall_emotion for w in ["fear", "anxiety", "panic", "dread", "恐惧", "焦虑"]):
        c = camera.get("panic_handheld", {})
        suggestions.append(f"  Camera: {c.get('name', '')} — {c.get('prompt_keywords', '')}")
        c2 = camera.get("creeping_dolly", {})
        suggestions.append(f"  Camera: {c2.get('name', '')} — {c2.get('prompt_keywords', '')}")
    elif any(w in overall_emotion for w in ["peace", "calm", "serene", "平静", "宁静", "温柔"]):
        c = camera.get("floating", {})
        suggestions.append(f"  Camera: {c.get('name', '')} — {c.get('prompt_keywords', '')}")
    elif any(w in overall_emotion for w in ["awe", "wonder", "震撼", "壮观"]):
        c = camera.get("architectural_reveal", {})
        suggestions.append(f"  Camera: {c.get('name', '')} — {c.get('prompt_keywords', '')}")
    else:
        c = camera.get("floating", {})
        suggestions.append(f"  Camera: {c.get('name', '')} — {c.get('prompt_keywords', '')}")

    # Narrative-based suggestions
    narratives = match_narratives(all_text)
    if narratives:
        nar = narratives[0]
        name = nar.get("name") or nar.get("name_en") or ""
        arc = nar.get("emotional_arc", {})
        if isinstance(arc, dict):
            stages = arc.get("stages", [])
            if stages:
                suggestions.append(f"  Narrative: {name} — emotional arc: {' → '.join(str(s) for s in stages[:4])}")

    # Style preset from prompt guide
    style_presets = _prompt_guide.get("style_presets", {})
    visual_style = dream_script.get("visual_style", "surreal").lower()
    preset = style_presets.get(visual_style) or style_presets.get("surreal", {})
    if preset:
        keywords = preset.get("keywords", [])
        if keywords:
            suggestions.append(f"  Style keywords: {', '.join(keywords[:6])}")
        ref_films = preset.get("reference_films", [])
        if ref_films:
            suggestions.append(f"  Reference: {', '.join(ref_films[:3])}")
        neg = preset.get("negative_prompt", "")
        if neg:
            suggestions.append(f"  Avoid: {neg[:100]}")

    # Emotion-to-visual mapping
    emotion_map = _prompt_guide.get("emotion_to_visual", {})
    for emotion_key, visual in emotion_map.items():
        if emotion_key in overall_emotion:
            if isinstance(visual, dict):
                cam = visual.get("camera", "")
                light = visual.get("lighting", "")
                color = visual.get("color", "")
                motion = visual.get("motion", "")
                if cam:
                    suggestions.append(f"  Emotion-camera: {cam}")
                if light:
                    suggestions.append(f"  Emotion-lighting: {light}")
                if color:
                    suggestions.append(f"  Emotion-color: {color}")
                if motion:
                    suggestions.append(f"  Emotion-motion: {motion}")
            break

    return "\n".join(suggestions) if len(suggestions) > 1 else ""
