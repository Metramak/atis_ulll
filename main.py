"""
ATIS Generator Server v1.0

Endpoints:
  GET  /gen    — голосовой текст для vATIS (ALPHA, ILS ZULU, точки, MPS)
  GET  /text   — текст для vATIS (A, ILS Z, числа цифрами)
  GET  /es     — для EuroScope (METAR с aviationweather.gov)
  GET  /api/config  — прочитать сохранённый конфиг
  POST /api/config  — сохранить конфиг из веб-UI
  GET  /       — веб-UI
"""

import re, json, pathlib
from fastapi import FastAPI, Query
from fastapi.responses import PlainTextResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Request
from typing import Optional, List
import urllib.request, urllib.error

app = FastAPI(title="ATIS Generator", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

BASE_DIR   = pathlib.Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
CONFIG_FILE = BASE_DIR / "config.json"

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ══════════════════════════════════════════════════════════════
# КОНФИГ — читается/пишется в config.json
# ══════════════════════════════════════════════════════════════

DEFAULT_CONFIG = {
    "icao": "ULLI", "arr": "28L", "dep": "28R", "app": "ILS",
    "tl": "",       "pressure": "QNH",
    "lvp": False,   "birds": False, "slippery": False,
    "reduced_min": False, "segregated": False, "min_rwy_occup": False,
    "closed_rwy": "", "closed_twy": "", "simult": "",
    "dep_freq": "", "remarks": "", "freetext": "",
}

def load_config(icao: str = "ULLI") -> dict:
    """Возвращает конфиг для конкретного аэропорта."""
    key = icao.upper()
    if CONFIG_FILE.exists():
        try:
            all_cfg = json.loads(CONFIG_FILE.read_text())
            # Поддержка старого формата (плоский dict без вложенности по ICAO)
            if "icao" in all_cfg:
                all_cfg = {"ULLI": all_cfg}
            return {**DEFAULT_CONFIG, "icao": key, **all_cfg.get(key, {})}
        except Exception:
            pass
    return {**DEFAULT_CONFIG, "icao": key}

def save_config(data: dict, icao: str = "ULLI"):
    """Сохраняет конфиг для конкретного аэропорта, не трогая остальные."""
    key = icao.upper()
    all_cfg = {}
    if CONFIG_FILE.exists():
        try:
            all_cfg = json.loads(CONFIG_FILE.read_text())
            if "icao" in all_cfg:        # миграция старого формата
                all_cfg = {"ULLI": all_cfg}
        except Exception:
            pass
    all_cfg[key] = {**DEFAULT_CONFIG, "icao": key, **data}
    CONFIG_FILE.write_text(json.dumps(all_cfg, ensure_ascii=False, indent=2))


# ══════════════════════════════════════════════════════════════
# METAR FETCH (для EuroScope)
# ══════════════════════════════════════════════════════════════

def fetch_metar(icao: str) -> Optional[str]:
    """
    Пробует несколько источников METAR по порядку.
    Возвращает первую успешно полученную строку или None.
    """
    icao = icao.upper()

    # Список источников: (url, парсер)
    # Парсер принимает текст ответа и возвращает строку METAR или None
    def _parse_raw_line(text: str) -> Optional[str]:
        """Ищем строку начинающуюся с ИКАО (4 заглавных буквы)"""
        for line in text.strip().splitlines():
            line = line.strip()
            if re.match(r'^[A-Z]{4}\s+\d{6}Z', line):
                return line
        return None

    def _parse_json(text: str) -> Optional[str]:
        """aviationweather JSON: [{rawOb: "ULLI ..."}]"""
        import json as _json
        try:
            data = _json.loads(text)
            if isinstance(data, list) and data:
                return data[0].get("rawOb") or data[0].get("raw_text")
            if isinstance(data, dict):
                return data.get("rawOb") or data.get("raw_text")
        except Exception:
            pass
        return None

    sources = [
        # 1. VATSIM METAR API — лучший для симуляции, включает российские аэропорты
        (f"https://metar.vatsim.net/metar.php?id={icao}",
         _parse_raw_line),
        # 2. aviationweather.gov — новый API (JSON)
        (f"https://aviationweather.gov/api/data/metar?ids={icao}&format=json&hours=1",
         _parse_json),
        # 3. aviationweather.gov — raw text
        (f"https://aviationweather.gov/api/data/metar?ids={icao}&format=raw",
         _parse_raw_line),
        # 4. NOAA text file
        (f"https://tgftp.nws.noaa.gov/data/observations/metar/stations/{icao}.TXT",
         _parse_raw_line),
    ]

    headers = {
        "User-Agent": "ATIS-Generator/1.0",
        "Accept": "text/plain, application/json, */*",
    }

    for url, parser in sources:
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                text = resp.read().decode("utf-8", errors="replace").strip()
                result = parser(text)
                if result:
                    return result
        except Exception:
            continue

    return None


from airports import (
    AIRPORT_NAMES, AIRPORT_TL_RULES, MAGNETIC_VARIATION,
    APPROACH_SUFFIX, SUFFIXED_APPROACHES,
)
from tables import (
    PHONETIC, RWY_DEPOSIT, RWY_EXTENT, SURFACE_FRICTION_TABLE, WX_CODES,
)


# ══════════════════════════════════════════════════════════════
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ══════════════════════════════════════════════════════════════

def airport_name(icao: str) -> str:
    return AIRPORT_NAMES.get(icao.upper(), icao.upper())

def phonetic(letter: str) -> str:
    return PHONETIC.get(letter.upper(), letter.upper())

_DIGIT_WORDS = ['ZERO','ONE','TWO','THREE','FOUR','FIVE','SIX','SEVEN','EIGHT','NINE']

def spell_digits(n) -> str:
    """str или int. Строка сохраняет ведущие нули: '060' → 'ZERO SIX ZERO'."""
    s = str(n) if isinstance(n, str) else str(abs(n))
    return ' '.join(_DIGIT_WORDS[int(d)] for d in s)

def spell_frequency_voice(freq: str) -> str:
    parts = freq.split('.')
    left = spell_digits(int(parts[0]))
    if len(parts) == 2:
        right = ' '.join(_DIGIT_WORDS[int(d)] for d in parts[1])
        return f"{left} DECIMAL {right}"
    return left

def mu_to_category(mu: float) -> str:
    for lo, hi, cat in SURFACE_FRICTION_TABLE:
        if lo <= mu < hi:
            return cat
    return "UNRELIABLE"

def spell_runway_voice(rwy: str) -> str:
    rwy = rwy.upper().strip()
    sfx = {"L": "LEFT", "R": "RIGHT", "C": "CENTER"}
    return f"{rwy[:-1]} {sfx[rwy[-1]]}" if rwy and rwy[-1] in sfx else rwy

def spell_runway_text(rwy: str) -> str:
    return rwy.upper().strip()

def build_approach_voice(app_type: str, arr: str, icao: str = "") -> tuple:
    a = app_type.upper()
    sfx = APPROACH_SUFFIX.get(icao.upper(), {}).get(arr.upper())
    if sfx and a in SUFFIXED_APPROACHES:
        voice_sfx = {"Z": "ZULU", "Y": "YANKEE"}.get(sfx, sfx)
        return a, voice_sfx
    return a, ""

def build_approach_text(app_type: str, arr: str, icao: str = "") -> tuple:
    a = app_type.upper()
    sfx = APPROACH_SUFFIX.get(icao.upper(), {}).get(arr.upper())
    if sfx and a in SUFFIXED_APPROACHES:
        return a, sfx
    return a, ""

def extract_time(raw: str) -> str:
    m = re.search(r'\b\d{2}(\d{4})Z\b', raw)
    return m.group(1) if m else ""

def fmt_temp(t: str) -> str:
    return f"MINUS {int(t[1:])}" if t.startswith("M") else str(int(t))


# ══════════════════════════════════════════════════════════════
# СОСТОЯНИЕ ВПП
# ══════════════════════════════════════════════════════════════

def parse_depth(code: str) -> Optional[str]:
    if '//' in code: return None
    val = int(code)
    if val == 0:  return "LESS THAN 1 MILLIMETER"
    if val <= 90: return f"{val} MILLIMETERS"
    special = {92:"10 CENTIMETERS",93:"15 CENTIMETERS",94:"20 CENTIMETERS",
               95:"25 CENTIMETERS",96:"30 CENTIMETERS",97:"35 CENTIMETERS"}
    return special.get(val)

def parse_friction_code(code: str) -> Optional[str]:
    if '//' in code or code == '99': return None
    legacy = {'91':'POOR','92':'MEDIUM TO POOR','93':'MEDIUM','94':'MEDIUM TO GOOD','95':'GOOD'}
    if code in legacy:
        return f"ESTIMATED SURFACE FRICTION {legacy[code]}"
    try:
        val = int(code)
        if 0 <= val <= 90:
            return f"ESTIMATED SURFACE FRICTION {mu_to_category(val / 100.0)}"
    except ValueError:
        pass
    return None

def parse_rwy_states(raw: str) -> List[dict]:
    states = []
    for m in re.finditer(r'\bR(\d{2}[LRC]?)/(?:(CLRD)(\d{2})|([\d/]{6}))\b', raw):
        rwy_code = m.group(1)
        if m.group(2) == 'CLRD':
            # R24/CLRD63 — ВПП расчищена, цифры = коэффициент сцепления
            friction = parse_friction_code(m.group(3))
            states.append({'rwy': rwy_code, 'all_rwys': rwy_code == '88',
                           'deposit': 'CLEAR AND DRY', 'extent': None,
                           'depth': None, 'friction': friction})
        else:
            data = m.group(4)
            if len(data) < 6: continue
            deposit  = RWY_DEPOSIT.get(data[0]) if data[0] != '/' else None
            extent   = RWY_EXTENT.get(data[1])  if data[1] != '/' else None
            depth    = parse_depth(data[2:4])   if '//' not in data[2:4] else None
            friction = parse_friction_code(data[4:6])
            if data[2:4] in ('98', '99'): deposit = None; extent = None; depth = None
            states.append({'rwy': rwy_code, 'all_rwys': rwy_code == '88',
                           'deposit': deposit, 'extent': extent,
                           'depth': depth, 'friction': friction})
    return states

def format_rwy_state(state: dict, voice: bool = False) -> str:
    parts = []
    if state.get('deposit'):  parts.append(state['deposit'])
    if state.get('extent'):   parts.append(state['extent'])
    if state.get('depth'):    
        if state.get('depth') != "LESS THAN 1 MILLIMETER":
            parts.append(state['depth'])
    if state.get('friction'): parts.append(state['friction'])
    if not parts: return ""
    return (", " if voice else " ").join(parts)

def get_rwy_state_text(states: List[dict], rwy: str, voice: bool = False) -> Optional[str]:
    rwy_up = rwy.upper()
    for s in states:
        if s['rwy'] == rwy_up[:2] or s['rwy'] == rwy_up:
            return format_rwy_state(s, voice)
    for s in states:
        if s['all_rwys']:
            return format_rwy_state(s, voice)
    return None


# ══════════════════════════════════════════════════════════════
# ЯВЛЕНИЯ ПОГОДЫ
# ══════════════════════════════════════════════════════════════

def parse_weather_phenomena(text: str) -> Optional[str]:
    found = []
    for code, phrase in WX_CODES:
        # Многословные (OBST OBSC, MT OBSC, MAST OBSC) — поиск подстроки
        if ' ' in code:
            if code in text:
                found.append(phrase)
            continue
        # Для кодов без интенсивности (SN, RA...) запрещаем предшествующие +/-/буквы
        # Для +/-/VC кодов — разрешаем только если перед ними пробел или начало
        pattern = r'(?<![A-Z+\-])' + re.escape(code) + r'(?![A-Z])'
        if re.search(pattern, text):
            found.append(phrase)
    return " ".join(found) if found else None


# ══════════════════════════════════════════════════════════════
# ПАРСЕР METAR
# ══════════════════════════════════════════════════════════════

def parse_metar(raw: str, icao: str = "ULLI") -> dict:
    if not raw: return {}
    main_raw = re.split(r'\b(NOSIG|TEMPO|BECMG)\b', raw)[0]
    r = {"raw": raw, "time": extract_time(main_raw)}
    is_cavok = bool(re.search(r'\bCAVOK\b', main_raw))
    r["cavok"] = is_cavok

    # ── Ветер (KT или MPS) ──
    wm = re.search(r'(\d{3}|VRB)(\d{2,3})(?:G(\d{2,3}))?(KT|MPS)\b', main_raw)
    vw = re.search(r'\b(\d{3})V(\d{3})\b', main_raw)
    if wm:
        d, sp, g, unit = wm.group(1), int(wm.group(2)), wm.group(3), wm.group(4)
        unit_word = "METERS PER SECOND" if unit == "MPS" else "KNOTS"
        r["wind_unit"] = unit
        if sp == 0:
            r["wind"] = "WIND CALM"
        elif vw:
            # Диапазон направлений — применяем склонение к обоим краям
            variation = MAGNETIC_VARIATION.get(icao.upper(), 0)
            fr_mag = (int(vw.group(1)) - variation) % 360 or 360
            to_mag = (int(vw.group(2)) - variation) % 360 or 360
            speed = f"{sp} GUSTING {int(g)} {unit_word}" if g else f"{sp} {unit_word}"
            r["wind"] = f"WIND VARIABLE BETWEEN {fr_mag:03d} AND {to_mag:03d} DEGREES {speed}"
        else:
            if d == "VRB":
                ds = "VARIABLE"
            else:
                variation = MAGNETIC_VARIATION.get(icao.upper(), 0)
                deg = (int(d) - variation) % 360
                if deg == 0:
                    deg = 360
                ds = f"{deg:03d} DEGREES"
            if g:
                r["wind"] = f"WIND {ds} {sp} GUSTING {int(g)} {unit_word}"
            else:
                r["wind"] = f"WIND {ds} {sp} {unit_word}"

    # ── RVR ──
    rvrs = []
    for m in re.finditer(r'R(\d{2}[LRC]?)/([PM]?\d{4})(?:V([PM]?\d{4}))?([UDN])?(?:FT?)?(?=\s|$)', main_raw):
        rwy, lo_raw, hi_raw = m.group(1), m.group(2), m.group(3)
        lo = lo_raw.lstrip('PM')
        if hi_raw:
            rvrs.append(f"RUNWAY {rwy} VISUAL RANGE {lo} TO {hi_raw.lstrip('PM')} METERS")
        elif lo_raw.startswith('P'):
            rvrs.append(f"RUNWAY {rwy} VISUAL RANGE MORE THAN {lo} METERS")
        elif lo_raw.startswith('M'):
            rvrs.append(f"RUNWAY {rwy} VISUAL RANGE LESS THAN {lo} METERS")
        else:
            trend_map = {'U': ' INCREASING', 'D': ' DECREASING', 'N': ''}
            trend_suffix = trend_map.get(m.group(4) or '', '')
            rvrs.append(f"RUNWAY {rwy} VISUAL RANGE {lo} METERS{trend_suffix}")
    if rvrs: r["rvr"] = " ".join(rvrs)

    # ── Видимость ──
    if not is_cavok:
        # \b(\d{4})\b — ровно 4 цифры как отдельное слово; Q1012 не совпадёт (Q — word char)
        vm = re.search(r'\b(\d{4})\b', main_raw)
        if vm and not re.search(rf'Q{vm.group(1)}', main_raw):
            vis = int(vm.group(1))
            if vis >= 9999:   r["visibility"] = "VISIBILITY MORE THAN 10 KILOMETERS"
            elif vis >= 5000: r["visibility"] = f"VISIBILITY {vis // 1000} KILOMETERS"
            else:             r["visibility"] = f"VISIBILITY {vis} METERS"
            # Минимальная видимость с направлением (п.1.5.2): напр. 2100 1400SW
            min_vm = re.search(
                r'\b(\d{4})(N|NE|E|SE|S|SW|W|NW)\b', main_raw)
            if min_vm:
                min_vis = int(min_vm.group(1))
                min_dir = min_vm.group(2)
                r["visibility_min"] = f"MINIMUM VISIBILITY {min_vis} METERS {min_dir}"

    # ── Облачность ──
    if not is_cavok:
        cm = {"FEW":"FEW","SCT":"SCATTERED","BKN":"BROKEN","OVC":"OVERCAST"}
        clouds = []
        for m in re.finditer(r'(FEW|SCT|BKN|OVC)(\d{3})(CB|TCU)?', main_raw):
            metres = int(m.group(2)) * 30
            layer  = f"{cm[m.group(1)]} {metres} METERS"
            if m.group(3) == "CB":    layer += " CUMULONIMBUS"
            elif m.group(3) == "TCU": layer += " TOWERING CUMULUS"
            clouds.append(layer)
        if re.search(r'\bNSC\b', main_raw):     r["clouds"] = "NO SIGNIFICANT CLOUDS"
        elif re.search(r'\bNCD\b', main_raw):   r["clouds"] = "NO CLOUDS DETECTED"
        elif re.search(r'\bSKC\b', main_raw):   r["clouds"] = "SKY CLEAR"
        elif re.search(r'\bVV///\b', main_raw): r["clouds"] = "VERTICAL VISIBILITY NOT OBSERVED"
        elif re.search(r'\bVV\d{3}\b', main_raw):
            mm = re.search(r'\bVV(\d{3})\b', main_raw)
            r["clouds"] = f"VERTICAL VISIBILITY {int(mm.group(1)) * 30} METERS"
        elif clouds: r["clouds"] = " ".join(clouds)

    # ── Явления погоды ──
    # Ищем в основной части метара
    wx = parse_weather_phenomena(main_raw)
    # Дополнительно ищем OBST OBSC в секции RMK (она может быть после NOSIG/BECMG/TEMPO)
    rmk_match = re.search(r'\bRMK\b(.+)', raw)
    if rmk_match:
        rmk_text = rmk_match.group(1)
        rmk_wx = parse_weather_phenomena(rmk_text)
        if rmk_wx:
            wx = (wx + ", " + rmk_wx) if wx else rmk_wx
    if wx: r["weather"] = wx

    # ── Температура / точка росы ──
    tm = re.search(r'\b(M?\d{2})\/(M?\d{2})\b', main_raw)
    if tm:
        r["temperature"] = fmt_temp(tm.group(1))
        r["dewpoint"]    = fmt_temp(tm.group(2))

    # ── QNH ──
    qm = re.search(r'Q(\d{4})', main_raw)
    if qm: r["qnh"] = qm.group(1)

    # ── RMK: QFE + остаток ──
    rmk_raw = re.search(r'\bRMK\b(.+)', raw)
    if rmk_raw:
        rmk_text = rmk_raw.group(1).strip()
        # QFE
        qfe_m = re.search(r'\bQFE(\d{3,4})(?:/(\d{3,4}))?\b', rmk_text)
        if qfe_m:
            r["qfe_mmhg"] = qfe_m.group(1)
            r["qfe_hpa"]  = qfe_m.group(2) or None
        # Остаток RMK: убираем QFE и известные коды погоды (они уже в weather)
        rmk_rest = re.sub(r'\bQFE\d{3,4}(?:/\d{3,4})?\b', '', rmk_text)
        # Убираем токены погоды, которые уже обработаны parse_weather_phenomena
        for code, _ in WX_CODES:
            if ' ' in code:  # многословные: OBST OBSC и т.п.
                rmk_rest = rmk_rest.replace(code, '')
            else:
                rmk_rest = re.sub(rf'(?<![A-Z+\-])\b{re.escape(code)}\b(?![A-Z])', '', rmk_rest)
        rmk_rest = ' '.join(rmk_rest.split())  # схлопываем пробелы
        if rmk_rest:
            r["rmk"] = rmk_rest

    # ── Windshear (п.1.11.2 — только WS Rxx и WS ALL RWY) ──
    ws_parts = []
    for wst in re.finditer(r'\bWS\s+(ALL\s+RWY|R\d{2}[LRC]?)\b', main_raw):
        loc = wst.group(1).strip()
        if loc.upper().startswith("ALL"):
            ws_parts.append("WINDSHEAR ALL RUNWAYS")
        else:
            ws_parts.append(f"WINDSHEAR RUNWAY {loc.lstrip('R')}")
    if ws_parts: r["windshear"] = " ".join(ws_parts)

    r["rwy_states"] = parse_rwy_states(main_raw)
    r["trend"]      = parse_trend(raw, icao)

    # ── Недавние явления погоды (RE...) ──
    re_parts = []
    for m in re.finditer(r'\bRE([A-Z+\-]{2,})\b', main_raw):
        wx_code = m.group(1)
        phrase = None
        for code, p in WX_CODES:
            if ' ' in code: continue
            if wx_code == re.sub(r'[+\-]', '', code).lstrip('VC'):
                phrase = p
                break
            if wx_code == code.lstrip('+-').lstrip('VC'):
                phrase = p
                break
        if phrase:
            re_parts.append(f"RECENT {phrase}")
        else:
            re_parts.append(f"RECENT {wx_code}")
    if re_parts:
        r["recent_wx"] = " ".join(re_parts)

    return r


# ══════════════════════════════════════════════════════════════
# TREND
# ══════════════════════════════════════════════════════════════

def parse_trend_section(text: str, icao: str = "ULLI") -> str:
    parts = []
    text = re.sub(r'\b\d{4}/\d{4}\b', '', text)
    text = re.sub(r'\b(?:FM|TL|AT)\d{4}\b', '', text).strip()
    wm = re.search(r'(\d{3}|VRB)(\d{2,3})(?:G(\d{2,3}))?(KT|MPS)\b', text)
    if wm:
        d, sp, g, unit = wm.group(1), int(wm.group(2)), wm.group(3), wm.group(4)
        uw = "METERS PER SECOND" if unit == "MPS" else "KNOTS"
        if d == "VRB":
            ds = "VARIABLE"
        else:
            variation = MAGNETIC_VARIATION.get(icao.upper(), 0)
            deg = (int(d) - variation) % 360
            if deg == 0: deg = 360
            ds = f"{deg:03d} DEGREES"
        if sp == 0:  parts.append("WIND CALM")
        elif g:      parts.append(f"WIND {ds} {sp} GUSTING {int(g)} {uw}")
        else:        parts.append(f"WIND {ds} {sp} {uw}")
    if re.search(r'\bCAVOK\b', text):
        parts.append("CAVOK")
    else:
        vm = re.search(r'(?:^|\s)(\d{4})(?:\s|$)', text)
        if vm:
            vis = int(vm.group(1))
            if not re.search(rf'Q{vm.group(1)}', text):
                if vis >= 9999:   parts.append("VISIBILITY GREATER THAN 10 KILOMETERS")
                elif vis >= 5000: parts.append(f"VISIBILITY {vis // 1000} KILOMETERS")
                else:             parts.append(f"VISIBILITY {vis} METERS")
        wx = parse_weather_phenomena(text)
        if wx: parts.append(wx)
        cm = {"FEW":"FEW","SCT":"SCATTERED","BKN":"BROKEN","OVC":"OVERCAST"}
        clouds = [f"{cm[m.group(1)]} {int(m.group(2))*30} METERS"
                  for m in re.finditer(r'(FEW|SCT|BKN|OVC)(\d{3})', text)]
        if re.search(r'\bNSC\b', text):   parts.append("NO SIGNIFICANT CLOUD")
        elif re.search(r'\bSKC\b', text): parts.append("SKY CLEAR")
        elif clouds:                       parts.append("CLOUDS " + " ".join(clouds))
    return " ".join(parts)

def parse_trend(raw: str, icao: str = "ULLI") -> Optional[str]:
    if re.search(r'\bNOSIG\b', raw): return "NOSIG"
    results = []
    for m in re.finditer(r'\b(TEMPO|BECMG)\b(.*?)(?=\bTEMPO\b|\bBECMG\b|$)', raw, re.DOTALL):
        label = "TEMPORARILY" if m.group(1) == "TEMPO" else "BECOMING"
        cond  = parse_trend_section(m.group(2).strip(), icao)
        if cond: results.append(f"{label} {cond}")
    return " ".join(results) if results else None


# ══════════════════════════════════════════════════════════════
# ЭШЕЛОН ПЕРЕХОДА
# ══════════════════════════════════════════════════════════════

def auto_transition_level(icao: str, qnh_str: Optional[str]) -> Optional[str]:
    rules = AIRPORT_TL_RULES.get(icao.upper())
    if not rules or not qnh_str: return None
    try:
        q = int(qnh_str)
    except ValueError:
        return None
    for lo, hi, tl in rules:
        if lo <= q <= hi: return tl
    return None


# ══════════════════════════════════════════════════════════════
# ПОСТРОИТЕЛЬ ATIS
# ══════════════════════════════════════════════════════════════

def build_atis(
    icao: str, info: str, metar_data: dict,
    arr: Optional[str], dep: Optional[str], app: Optional[str],
    tl: Optional[str], pressure_type: str,
    lvp: bool, birds: bool, slippery: bool, reduced_min: bool,
    closed_rwy: Optional[str], closed_twy: Optional[str],
    simult: Optional[str], segregated: bool,
    dep_freq: Optional[str], remarks: Optional[str], freetext: Optional[str],
    min_rwy_occup: bool = False, voice: bool = True,
) -> str:
    rwy_states = metar_data.get("rwy_states", [])

    if voice:
        info_str   = phonetic(info)
        spell_rwy  = spell_runway_voice
        app_str_fn = build_approach_voice
        sep        = ". "
        wx_sep     = ", "
    else:
        info_str   = info.upper()
        spell_rwy  = spell_runway_text
        app_str_fn = build_approach_text
        sep        = " "
        wx_sep     = " "

    sentences = []

    # 1. Заголовок
    hdr = f"{airport_name(icao)} ATIS INFORMATION {info_str}"
    t = metar_data.get("time", "")
    if t: hdr += ("" if voice else " ") + f" {t}" + ("" if voice else "Z")
    sentences.append(hdr)

    # Одна ВПП для обоих направлений?
    same_rwy = arr and dep and arr.upper() == dep.upper()

    # 2. ВПП прилёта + состояние
    if arr:
        app_s, app_sfx = app_str_fn(app or "ILS", arr, icao)
        approach_word = f"APPROACH {app_sfx}" if app_sfx else "APPROACH"
        arr_line = f"EXPECT {app_s} {approach_word} RUNWAY {spell_rwy(arr)}"
        # Состояние показываем здесь только если ВПП разные
        # (если одна — покажем один раз после dep)
        if not same_rwy:
            rws = get_rwy_state_text(rwy_states, arr, voice)
            if rws: arr_line += (", " if voice else " ") + rws
        sentences.append(arr_line)

    # 3. ВПП вылета + состояние
    if dep:
        dep_line = f"FOR DEPARTURE RUNWAY {spell_rwy(dep)}"
        rws = get_rwy_state_text(rwy_states, dep, voice)
        if rws: dep_line += (", " if voice else " ") + rws
        sentences.append(dep_line)
        

    # 4. Эшелон перехода
    if tl: sentences.append(f"TRANSITION LEVEL {tl}")

    # Segregated только если реально две разные ВПП
    if segregated and not same_rwy:
        sentences.append("SEGREGATED PARALLEL OPERATIONS IN USE")

    # 5. Спецусловия
    if lvp:       sentences.append("LOW VISIBILITY PROCEDURES IN USE")
    if slippery:  sentences.append(
        "APRON AND TAXIWAYS ARE SLIPPERY, TAXI WITH CAUTION" if voice
        else "APRON AND TAXIWAYS ARE SLIPPERY TAXI WITH CAUTION")
    if birds:     sentences.append("BIRD STRIKE HAZARD IN VICINITY OF AERODROME AND ON FINAL")
    if reduced_min: sentences.append("REDUCED RUNWAY VISUAL RANGE MINIMA IN USE")
    if min_rwy_occup: sentences.append("MINIMUM RUNWAY OCCUPANCY TIME")
    if closed_rwy:  sentences.append(f"RUNWAY {spell_rwy(closed_rwy)} CLOSED")
    if closed_twy:  sentences.append(f"TAXIWAY {closed_twy.upper()} CLOSED")
    if simult == "dep":    sentences.append("DEPENDENT SIMULTANEOUS APPROACHES IN USE")
    elif simult == "indep": sentences.append("INDEPENDENT SIMULTANEOUS APPROACHES IN USE")

    # 6. Сдвиг ветра
    if metar_data.get("windshear"):
        sentences.append(metar_data["windshear"])

    # 7. Погода
    if metar_data.get("wind"):
        if metar_data.get("cavok"):
            sentences.append(f"{metar_data['wind']}{wx_sep}CAVOK")
        else:
            wp = [metar_data["wind"]]
            if metar_data.get("rvr"):          wp.append(metar_data["rvr"])
            if metar_data.get("visibility"):   wp.append(metar_data["visibility"])
            if metar_data.get("visibility_min"): wp.append(metar_data["visibility_min"])
            if metar_data.get("weather"):      wp.append(metar_data["weather"])
            if metar_data.get("recent_wx"):    wp.append(metar_data["recent_wx"])
            if metar_data.get("clouds"):       wp.append(f"CLOUDS {metar_data['clouds']}")
            sentences.append(wx_sep.join(wp))

    # 8. Температура / точка росы
    if metar_data.get("temperature") and metar_data.get("dewpoint"):
        sentences.append(
            f"TEMPERATURE {metar_data['temperature']}{wx_sep}"
            f"DEW POINT {metar_data['dewpoint']}")

    # 9. QNH
    if metar_data.get("qnh"):
        if voice:
            sentences.append(f"QNH {metar_data['qnh']} HECTOPASCALS")
        else:
            sentences.append(f"QNH {metar_data['qnh']} HPA")

    # 10. Частота после вылета
    if dep_freq:
        if voice:
            sentences.append(f"DEPARTURE FREQUENCY {spell_frequency_voice(dep_freq)}")
        else:
            sentences.append(f"DEPARTURE FREQUENCY {dep_freq}")

    # 11. Remarks / freetext
    if remarks:  sentences.append(remarks.strip())
    if freetext: sentences.append(freetext.strip())

    # 12. TREND
    if metar_data.get("trend"): sentences.append(metar_data["trend"])

    # 13. RMK — QFE и остаток, всё в конце до ACKNOWLEDGE
    if metar_data.get("qfe_mmhg"):
        mmhg = metar_data["qfe_mmhg"]
        hpa  = metar_data.get("qfe_hpa")
        if voice:
            hpa_part = f", {hpa} HECTOPASCALS" if hpa else ""
            sentences.append(f"QFE {mmhg} MILLIMETERS OF MERCURY {hpa_part}")
        else:
            hpa_part = f"/{hpa}" if hpa else ""
            sentences.append(f"QFE {mmhg}{hpa_part}")
    if metar_data.get("rmk"):
        sentences.append(metar_data["rmk"])

    # 14. Концовка
    sentences.append(f"ACKNOWLEDGE INFORMATION {info_str}")

    result = sep.join(sentences)

    # 14. Voice post-processing: spell digits
    if voice:
        result = re.sub(r'\b(\d{4})Z\b',
                        lambda m: spell_digits(int(m.group(1))) + ' ZULU', result)
        result = re.sub(r'\b(\d+)\b',
                        lambda m: spell_digits(m.group(1)), result)

    return result


# ══════════════════════════════════════════════════════════════
# ОБЩИЙ ХЕЛПЕР
# ══════════════════════════════════════════════════════════════

def _build_from_cfg(cfg: dict, info: str, metar_raw: Optional[str], voice: bool) -> str:
    icao   = cfg.get("icao", "ULLI")
    md     = parse_metar(metar_raw, icao) if metar_raw else {}
    eff_tl = cfg.get("tl") or auto_transition_level(icao, md.get("qnh"))
    pt     = "QFE" if cfg.get("pressure") == "QFE" else "QNH"
    def f(k): return bool(cfg.get(k))
    return build_atis(
        icao=icao.upper(), info=info.upper(), metar_data=md,
        arr=cfg.get("arr") or None,
        dep=cfg.get("dep") or None,
        app=cfg.get("app") or "ILS",
        tl=eff_tl or None,
        pressure_type=pt,
        lvp=f("lvp"), birds=f("birds"), slippery=f("slippery"),
        reduced_min=f("reduced_min"), segregated=f("segregated"), min_rwy_occup=f("min_rwy_occup"),
        closed_rwy=cfg.get("closed_rwy") or None,
        closed_twy=cfg.get("closed_twy") or None,
        simult=cfg.get("simult") or None,
        dep_freq=cfg.get("dep_freq") or None,
        remarks=cfg.get("remarks") or None,
        freetext=cfg.get("freetext") or None,
        voice=voice,
    )

# ══════════════════════════════════════════════════════════════
# ENDPOINTS
# ══════════════════════════════════════════════════════════════

def _common_params():
    """Общие параметры для gen/text/es."""
    pass

def _apply_url_overrides(cfg, icao, arr, dep, app_type):
    if icao:     cfg["icao"] = icao.upper()
    if arr:      cfg["arr"]  = arr.upper()
    if dep:      cfg["dep"]  = dep.upper()
    if app_type: cfg["app"]  = app_type
    return cfg


@app.get("/gen", response_class=PlainTextResponse,
         summary="Голосовой ATIS для vATIS")
async def gen_voice(
    info:     str           = Query("A"),
    metar:    Optional[str] = Query(None),
    icao:     Optional[str] = Query(None),
    arr:      Optional[str] = Query(None),
    dep:      Optional[str] = Query(None),
    app:      Optional[str] = Query(None),
):
    cfg = _apply_url_overrides(load_config(icao or "ULLI"), icao, arr, dep, app)
    text = _build_from_cfg(cfg, info, metar, voice=True)
    return PlainTextResponse(text, media_type="text/plain; charset=utf-8")


@app.get("/text", response_class=PlainTextResponse,
         summary="Текстовый ATIS для vATIS")
async def gen_text(
    info:     str           = Query("A"),
    metar:    Optional[str] = Query(None),
    icao:     Optional[str] = Query(None),
    arr:      Optional[str] = Query(None),
    dep:      Optional[str] = Query(None),
    app:      Optional[str] = Query(None),
):
    cfg = _apply_url_overrides(load_config(icao or "ULLI"), icao, arr, dep, app)
    text = _build_from_cfg(cfg, info, metar, voice=False)
    return PlainTextResponse(text, media_type="text/plain; charset=utf-8")



@app.get("/es",
         summary="ATIS для EuroScope (METAR берётся автоматически)")
async def gen_euroscope(
    info:  str           = Query("A"),
    icao:  Optional[str] = Query(None),
    arr:   Optional[str] = Query(None),
    dep:   Optional[str] = Query(None),
    metar: Optional[str] = Query(None),
    voice: bool          = Query(True),
):
    """
    Возвращает JSON-строку ("текст") — именно такой формат ожидает EuroScope.
    Content-Type: application/json
    Body: "PULKOVO ATIS INFORMATION ALPHA ..."
    """
    import json as _json
    cfg = _apply_url_overrides(load_config(icao or "ULLI"), icao, arr, dep, None)
    if not metar:
        metar = fetch_metar(cfg["icao"])
    if not metar:
        return JSONResponse(
            content=f"METAR NOT AVAILABLE FOR {cfg['icao']}",
            status_code=503)
    text = _build_from_cfg(cfg, info, metar, voice=voice)
    return PlainTextResponse(text, media_type="text/plain; charset=utf-8")


@app.get("/debug/metar", response_class=PlainTextResponse,
         summary="Диагностика: что сервер получает из источников METAR")
async def debug_metar(icao: str = Query("ULLI")):
    """Пробует каждый источник и показывает результат/ошибку."""
    import time, json as _json
    icao = icao.upper()
    lines = []

    def _p_raw(text):
        for line in text.strip().splitlines():
            line = line.strip()
            if re.match(r'^[A-Z]{4}\s+\d{6}Z', line):
                return line
        return None

    def _p_json(text):
        try:
            data = _json.loads(text)
            if isinstance(data, list) and data:
                return data[0].get("rawOb") or data[0].get("raw_text")
        except Exception:
            pass
        return None

    dbg_sources = [
        (f"https://metar.vatsim.net/metar.php?id={icao}", _p_raw, "VATSIM"),
        (f"https://aviationweather.gov/api/data/metar?ids={icao}&format=json&hours=1", _p_json, "AWG JSON"),
        (f"https://aviationweather.gov/api/data/metar?ids={icao}&format=raw", _p_raw, "AWG raw"),
        (f"https://tgftp.nws.noaa.gov/data/observations/metar/stations/{icao}.TXT", _p_raw, "NOAA"),
    ]
    hdr = {"User-Agent": "ATIS-Generator/1.0"}
    for url, parser, name in dbg_sources:
        t0 = time.time()
        try:
            req = urllib.request.Request(url, headers=hdr)
            with urllib.request.urlopen(req, timeout=8) as resp:
                text = resp.read().decode("utf-8", errors="replace").strip()
            result = parser(text)
            elapsed = time.time() - t0
            if result:
                lines.append(f"OK {name} ({elapsed:.1f}s): {result}")
            else:
                lines.append(f"? {name} ({elapsed:.1f}s): response ok but no METAR parsed\n  raw: {text[:120]}")
        except Exception as e:
            elapsed = time.time() - t0
            lines.append(f"ERR {name} ({elapsed:.1f}s): {e}")

    return PlainTextResponse("\n".join(lines))


@app.get("/api/config")
async def get_config(icao: str = Query("ULLI")):
    return JSONResponse(load_config(icao))


@app.post("/api/config")
async def post_config(request: Request, icao: str = Query("ULLI")):
    data = await request.json()
    save_config(data, icao)
    return JSONResponse({"status": "ok"})


@app.get("/")
async def index():
    f = STATIC_DIR / "index.html"
    if f.exists():
        return FileResponse(str(f), media_type="text/html")
    return PlainTextResponse("ATIS Generator v1 running.")

@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}