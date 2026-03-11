"""
Статические таблицы: коды погоды, состояние ВПП, фонетика.
Не требуют редактирования в штатной эксплуатации.
"""

PHONETIC = {
    'A':'ALPHA',  'B':'BRAVO',    'C':'CHARLIE', 'D':'DELTA',
    'E':'ECHO',   'F':'FOXTROT',  'G':'GOLF',    'H':'HOTEL',
    'I':'INDIA',  'J':'JULIETT',  'K':'KILO',    'L':'LIMA',
    'M':'MIKE',   'N':'NOVEMBER', 'O':'OSCAR',   'P':'PAPA',
    'Q':'QUEBEC', 'R':'ROMEO',    'S':'SIERRA',  'T':'TANGO',
    'U':'UNIFORM','V':'VICTOR',   'W':'WHISKEY', 'X':'XRAY',
    'Y':'YANKEE', 'Z':'ZULU',
}

RWY_DEPOSIT = {
    '0': 'CLEAR AND DRY',
    '1': 'DAMP',
    '2': 'WET',
    '3': 'COVERED WITH RIME OR FROST',
    '4': 'COVERED WITH DRY SNOW',
    '5': 'COVERED WITH WET SNOW',
    '6': 'COVERED WITH SLUSH',
    '7': 'COVERED WITH ICE',
    '8': 'COVERED WITH COMPACTED SNOW',
    '9': 'COVERED WITH FROZEN RUTS',
}

RWY_EXTENT = {
    '1': 'LESS THAN 10 PERCENT',
    '2': '11 TO 25 PERCENT',
    '5': '26 TO 50 PERCENT',
    '9': '51 TO 100 PERCENT',
}

# (min, max, friction)
SURFACE_FRICTION_TABLE = [
    (0.40, 1.01, "GOOD"),
    (0.36, 0.40, "MEDIUM TO GOOD"),
    (0.30, 0.36, "MEDIUM"),
    (0.26, 0.30, "MEDIUM TO POOR"),
    (0.17, 0.26, "POOR"),
    (0.00, 0.17, "UNRELIABLE"),
]

WX_CODES = [
    # RMK
    ("OBST OBSC", "OBSTACLES OBSCURED"),
    ("MAST OBSC", "MASTS OBSCURED"),
    ("MT OBSC",   "MOUNTAINS OBSCURED"),
    # FZ 
    ("FZRA",  "FREEZING RAIN"),
    ("FZDZ",  "FREEZING DRIZZLE"),
    ("FZFG",  "FREEZING FOG"),
    # TS
    ("+TSRA", "HEAVY THUNDERSTORM WITH RAIN"),
    ("-TSRA", "LIGHT THUNDERSTORM WITH RAIN"),
    ("TSRA",  "THUNDERSTORM WITH RAIN"),
    ("+TSSN", "HEAVY THUNDERSTORM WITH SNOW"),
    ("-TSSN", "LIGHT THUNDERSTORM WITH SNOW"),
    ("TSSN",  "THUNDERSTORM WITH SNOW"),
    ("+TSGR", "HEAVY THUNDERSTORM WITH HAIL"),
    ("-TSGR", "LIGHT THUNDERSTORM WITH HAIL"),
    ("TSGR",  "THUNDERSTORM WITH HAIL"),
    ("+TSGS", "HEAVY THUNDERSTORM WITH SMALL HAIL"),
    ("-TSGS", "LIGHT THUNDERSTORM WITH SMALL HAIL"),
    ("TSGS",  "THUNDERSTORM WITH SMALL HAIL"),
    ("VCTS",  "THUNDERSTORM IN VICINITY"),
    ("TS",    "THUNDERSTORM"),
    # ── Ливни ────────────────────────────────────────────────────
    ("+SHRA", "HEAVY RAIN SHOWER"),
    ("-SHRA", "LIGHT RAIN SHOWER"),
    ("SHRA",  "RAIN SHOWER"),
    ("+SHSN", "HEAVY SNOW SHOWER"),
    ("-SHSN", "LIGHT SNOW SHOWER"),
    ("SHSN",  "SNOW SHOWER"),
    ("+SHGR", "HEAVY HAIL SHOWER"),
    ("-SHGR", "LIGHT HAIL SHOWER"),
    ("SHGR",  "HAIL SHOWER"),
    ("+SHGS", "HEAVY SMALL HAIL SHOWER"),
    ("-SHGS", "LIGHT SMALL HAIL SHOWER"),
    ("SHGS",  "SMALL HAIL SHOWER"),
    ("VCSH",  "SHOWERS IN VICINITY"),
    ("+SH",   "HEAVY SHOWERS"),
    ("-SH",   "LIGHT SHOWERS"),
    ("SH",    "SHOWERS"),
    # ── Осадки ───────────────────────────────────────────────────
    ("RASN", "RAIN AND SNOW"),
    ("+RA",  "HEAVY RAIN"),     ("-RA", "LIGHT RAIN"),    ("RA", "RAIN"),
    ("+SN",  "HEAVY SNOW"),     ("-SN", "LIGHT SNOW"),    ("SN", "SNOW"),
    ("+DZ",  "HEAVY DRIZZLE"),  ("-DZ", "LIGHT DRIZZLE"), ("DZ", "DRIZZLE"),
    ("GR",   "HAIL"),           ("GS",  "SMALL HAIL"),    ("SG", "SNOW GRAINS"),
    ("IC",   "ICE CRYSTALS"),   ("PL",  "ICE PELLETS"),
    # ── Метели и поземок ─────────────────────────────────────────
    ("BLSN",   "BLOWING SNOW"),       ("BLSA",   "BLOWING SAND"),
    ("BLDU",   "BLOWING DUST"),       ("VCBLSN", "BLOWING SNOW IN VICINITY"),
    ("VCBLSA", "BLOWING SAND IN VICINITY"),
    ("VCBLDU", "BLOWING DUST IN VICINITY"),
    ("DRSN",   "DRIFTING SNOW"),      ("DRSA",   "DRIFTING SAND"),
    ("DRDU",   "DRIFTING DUST"),
    # ── Туман ────────────────────────────────────────────────────
    ("MIFG",  "SHALLOW FOG"),   ("BCFG",  "PATCHES OF FOG"),
    ("PRFG",  "PARTIAL FOG"),   ("VCFG",  "FOG IN VICINITY"),
    ("FG",    "FOG"),
    # ── Прочие явления ухудшающие видимость ──────────────────────
    ("BR",    "MIST"),          ("HZ",    "HAZE"),
    ("FU",    "SMOKE"),         ("VA",    "VOLCANIC ASH"),
    ("VCVA",  "VOLCANIC ASH IN VICINITY"),
    ("SA",    "SAND"),          ("DU",    "DUST"),
    # ── Бури ─────────────────────────────────────────────────────
    ("+SS",   "HEAVY SANDSTORM"),       ("-SS",  "LIGHT SANDSTORM"),
    ("VCSS",  "SANDSTORM IN VICINITY"), ("SS", "SANDSTORM"),
    ("+DS",   "HEAVY DUSTSTORM"),       ("-DS",  "LIGHT DUSTSTORM"),
    ("VCDS",  "DUSTSTORM IN VICINITY"), ("DS", "DUSTSTORM"),
    # ── Прочие ───────────────────────────────────────────────────
    ("+FC",   "TORNADO"),                 ("VCFC",  "FUNNEL CLOUD IN VICINITY"),
    ("FC",    "FUNNEL CLOUD"),            ("PO",    "DUST WHIRLS"),
    ("VCPO",  "DUST WHIRLS IN VICINITY"), ("SQ", "SQUALL"),
]
