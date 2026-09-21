"""Bilingual (English + Arabic) strings and rendering helpers.

Every visible string exists in two variants:
  * English  -> rendered on the LEFT,  font-family: Comfortaa
  * Arabic   -> rendered on the RIGHT, font-family: 'VIP RAWY Regular'

Callers inside templates use ``t('KEY', **kw)`` / ``bt(en, ar)`` which return
ready HTML markup. The same helpers are reused for tooltips inside the
standalone folium map documents.
"""
import html

from markupsafe import Markup

EN_FONT = "'Comfortaa', 'Segoe UI', sans-serif"
AR_FONT = "'VIP RAWY Regular', 'Rawy', 'Tahoma', 'Segoe UI', sans-serif"

# --------------------------------------------------------------------------- #
# Dictionaries: templates use t('KEY', ...)
# --------------------------------------------------------------------------- #
EN = {
    # nav / misc
    "MODEL_NAME": "Farm Simulator",
    "MODEL_NAME_AR_EXTRA": "محاكي المزرعة",
    "PART1": "Part 1 - irrigation network",
    "PART1_AR": "الجزء الأول - شبكة الري",
    "UPLOAD_NEW": "Upload another file",
    "BACK_CONFIG": "Back to config",
    "BACK_ALL": "Back to all sectors",
    "HOME": "Home",
    "NEW_UPLOAD": "New upload",
    "OTHER_CONFIGS": "other configs",
    "LEGEND": "Legend",
    "AREA": "Area",
    "DIAMETER": "Diameter",
    "LENGTH": "Length",
    "ZONE": "Zone",
    "VALVE": "Valve",
    "PIPE": "Pipe",
    "SECTORS": "sectors",
    "ZONES": "zones",
    "VALVES": "valves",
    "MAJORS": "majors 50 mm",
    "MINORS": "minors 32 mm",

    # index
    "LOAD_TITLE": "Load a saved run",
    "LOAD": "Load",
    "LOAD_EMPTY": "No saved runs yet - upload a file first, the maps and results are saved automatically.",
    "UPLOAD_TITLE": "1. Upload your land",
    "UPLOAD_CTRL_TEXT": "Choose a KML or CSV file from Google Maps (boundaries + water point).",
    "UPLOAD_BTN": "Analyse the plot",
    "UPLOAD_RESULT_TITLE": "Upload Result",
    "UPLOAD_FIRST": "Upload First a File (csv/kml)",
    "FORMATS_TITLE": "Accepted formats",
    "FMT_KML": "KML - the classic Google Maps \u201cMy Maps\u201d export. Every Polygon is a boundary; Point(s) are the water marks.",
    "FMT_CSV": "CSV - one row per vertex with a header, e.g. lat,lon,name,type. Rows whose type is water mark the source; everything else is a boundary ring.",
    "FMT_WKT": "WKT CSV - a geometry column with POLYGON(...) and POINT(...) rows.",
    "ELEV_NOTE": "Elevation is read from the KML altitude when present. Without it, the basin is placed at the most favourable point near the water entry.",
    "WHAT_TITLE": "What Part 1 produces",
    "STEP_BASIN": "Basin - best spot near the water point at a favourable elevation.",
    "STEP_SECTORS": "Sectorisation - up to 5 config maps, every sector \u2264 10,000 m\u00b2, named S1, S2, \u2026",
    "STEP_ZONES": "Zonage - each sector splits into 3 equal zones Z1, Z2, Z3.",
    "STEP_VALVES": "Valves - one 50 mm valve on the first point of each zone.",
    "STEP_PIPES": "Piping - 90 mm principal from the max elevation through the basin; 50 mm majors to each zone valve; 32 mm minors from each valve to the zone supply point.",

    # result
    "BASIN_TITLE": "Basin placement",
    "BASIN_REC": "Recommended basin at",
    "DIST_WATER": "distance from water point",
    "ELEVATION": "elevation",
    "MAX_ELEV_IN": "max elevation inside land",
    "APPLY": "Apply",
    "LON": "X / Longitude",
    "LAT": "Y / Latitude",
    "DRAG_HINT": "Drag the brown marker on the map, or edit the coordinates, then Apply to move the basin.",
    "SECTOR_TITLE": "2. Sectorisation - choose a config",
    "SECTOR_SUB": "Every config splits the land into sectors \u2264 10,000 m\u00b2. Pick the layout you like best.",
    "USE_CONFIG": "Use this config",
    "EXISTING_TITLE": "2. Sectors already in your file",
    "EXISTING_SUB": "Your uploaded map already contains a sector layout covering the land, so no new suggestions were generated - we use it as-is.",
    "LAND_SURFACE": "Land surface",
    "WATER_POINT": "water point",
    "LG_BOUNDARY": "Land boundary",
    "LG_SECTOR": "Sector",
    "LG_BASIN": "Basin",
    "LG_WATER": "Water point",
    "LG_MAXELEV": "Max elevation",

    # config
    "CFG_TITLE": "Config",
    "CFG_SUB": "sectors of max 10,000 m\u00b2 - basin at",
    "FULL_MAP": "Full map - sectors, zones, valves and piping",
    "PRINCIPAL_90": "Principal 90mm",
    "SELECT_SECTOR": "Select a sector",
    "OPEN": "Open",
    "LG_ZONES": "Zones (Z1 orange, Z2 green, Z3 red)",
    "LG_P90": "Principal 90 mm",
    "LG_P50": "Major 50 mm",
    "LG_P32": "Minor 32 mm",
    "LG_VALVE": "Valve 50 mm",

    # sector
    "ZONES_OF": "Zones of",
    "PIPES_CARD": "Pipes in this card",
    "SPLIT_INFO": "split into {n} equal zones. The map shows boundaries, water point, basin, zones, valves and pipes.",
    "T_PRINCIPAL": "Principal",
    "T_MAJOR": "Major",
    "T_MINOR": "Minor",
    "D_90": "90 mm",
    "D_50": "50 mm",
    "D_32": "32 mm",
}

AR = {
    "MODEL_NAME": "محاكي المزرعة",
    "MODEL_NAME_AR_EXTRA": "محاكي المزرعة",
    "PART1": "الجزء الأول - شبكة الري",
    "PART1_AR": "الجزء الأول - شبكة الري",
    "UPLOAD_NEW": "رفع ملف آخر",
    "BACK_CONFIG": "العودة إلى التخطيط",
    "BACK_ALL": "العودة إلى جميع القطاعات",
    "HOME": "الرئيسية",
    "NEW_UPLOAD": "رفع جديد",
    "OTHER_CONFIGS": "تخطيطات أخرى",
    "LEGEND": "مفتاح الخريطة",
    "AREA": "المساحة",
    "DIAMETER": "القطر",
    "LENGTH": "الطول",
    "ZONE": "المنطقة",
    "VALVE": "الصمام",
    "PIPE": "الأنبوب",
    "SECTORS": "قطاعات",
    "ZONES": "مناطق",
    "VALVES": "صمامات",
    "MAJORS": "فرعيات رئيسية 50 مم",
    "MINORS": "فرعيات 32 مم",

    "LOAD_TITLE": "تحميل نتيجة محفوظة",
    "LOAD": "تحميل",
    "LOAD_EMPTY": "لا توجد نتائج محفوظة بعد - ارفع ملفاً أولاً، وتُحفظ الخرائط والنتائج تلقائياً.",
    "UPLOAD_TITLE": "1. رفع قطعة أرضك",
    "UPLOAD_CTRL_TEXT": "اختر ملف KML أو CSV من خرائط جوجل (الحدود + مصدر الماء).",
    "UPLOAD_BTN": "تحليل الأرض",
    "UPLOAD_RESULT_TITLE": "نتيجة الرفع",
    "UPLOAD_FIRST": "ارفَع الملف أولاً (csv/kml)",
    "FORMATS_TITLE": "الصيغ المقبولة",
    "FMT_KML": "KML - التصدير الكلاسيكي من خرائط جوجل \u201cخرائطي\u201d. كل مضلع Polygon هو حدود، ونقاط Point هي علامات مصدر الماء.",
    "FMT_CSV": "CSV - سطر لكل رأس مع ترويسة مثل lat,lon,name,type. الأسطر التي نوعها water تميّز مصدر الماء، والباقي حلقات للحدود.",
    "FMT_WKT": "WKT CSV - عمود geometry يحتوي على POLYGON(...) و POINT(...).",
    "ELEV_NOTE": "يُقرأ الارتفاع من بيانات KML عند توفّره. بدونه، يُوضع الحوض في أفضل نقطة قرب مدخل الماء.",
    "WHAT_TITLE": "ماذا يُنتج الجزء الأول",
    "STEP_BASIN": "الحوض - أفضل موقع قرب مصدر الماء مع ارتفاع مناسب.",
    "STEP_SECTORS": "القطاعيات - حتى 5 خرائط تخطيطات، كل قطاع \u2264 10,000 م\u00b2، وتسميته S1، S2، \u2026",
    "STEP_ZONES": "التقسيم - يُقسَّم كل قطاع إلى 3 مناطق متساوية Z1، Z2، Z3.",
    "STEP_VALVES": "الصمامات - صمام 50 مم عند أول نقطة في كل منطقة.",
    "STEP_PIPES": "الأنابيب - رئيسي 90 مم من أعلى ارتفاع عبر الحوض؛ فرعيات رئيسية 50 مم إلى كل صمام منطقة؛ فرعيات 32 مم من كل صمام إلى نقطة تزويد المنطقة.",

    "BASIN_TITLE": "موقع الحوض",
    "BASIN_REC": "الحوض الموصى به عند",
    "DIST_WATER": "المسافة من مصدر الماء",
    "ELEVATION": "الارتفاع",
    "MAX_ELEV_IN": "أقصى ارتفاع داخل الأرض",
    "APPLY": "تطبيق",
    "LON": "X / خط الطول",
    "LAT": "Y / خط العرض",
    "DRAG_HINT": "اسحب العلامة البنية على الخريطة، أو عدّل الإحداثيات ثم اضغط تطبيق، لتغيير موقع الحوض.",
    "SECTOR_TITLE": "2. القطاعيات - اختر تخطيطًا",
    "SECTOR_SUB": "يقسّم كل تخطيط الأرض إلى قطاعات \u2264 10,000 م\u00b2. اختر الشكل الأنسب لك.",
    "USE_CONFIG": "استخدم هذا التخطيط",
    "EXISTING_TITLE": "2. القطاعات موجودة في ملفك",
    "EXISTING_SUB": "ملفك يحتوي بالفعل على تقسيم قطاعات يغطي الأرض، لذلك لم يتم إنشاء اقتراحات جديدة - سيتم استخدامه كما هو.",
    "LAND_SURFACE": "مساحة الأرض",
    "WATER_POINT": "مصدر الماء",
    "LG_BOUNDARY": "حدود الأرض",
    "LG_SECTOR": "قطاع",
    "LG_BASIN": "حوض",
    "LG_WATER": "مصدر الماء",
    "LG_MAXELEV": "أقصى ارتفاع",

    "CFG_TITLE": "التخطيط",
    "CFG_SUB": "قطاعات بحد أقصى 10,000 م\u00b2 - الحوض عند",
    "FULL_MAP": "الخريطة الكاملة - القطاعات والمناطق والصمامات والأنابيب",
    "PRINCIPAL_90": "الأنبوب الرئيسي 90 مم",
    "SELECT_SECTOR": "اختر قطاعًا",
    "OPEN": "افتح",
    "LG_ZONES": "المناطق (Z1 برتقالي، Z2 أخضر، Z3 أحمر)",
    "LG_P90": "الرئيسي 90 مم",
    "LG_P50": "فرعي رئيسي 50 مم",
    "LG_P32": "فرعي 32 مم",
    "LG_VALVE": "صمام 50 مم",

    "ZONES_OF": "مناطق",
    "PIPES_CARD": "الأنابيب في هذه البطاقة",
    "SPLIT_INFO": "مقسّم إلى {n} مناطق متساوية. تُظهر الخريطة الحدود، ومصدر الماء، والحوض، والمناطق، والصمامات، والأنابيب.",
    "T_PRINCIPAL": "الرئيسي",
    "T_MAJOR": "فرعي رئيسي",
    "T_MINOR": "فرعي",
    "D_90": "90 مم",
    "D_50": "50 مم",
    "D_32": "32 مم",
}

# config names produced by the engine -> Arabic
CONFIG_NAMES = {
    "East-West strips": "شرائح شرق-غرب",
    "North-South strips": "شرائح شمال-جنوب",
    "Diagonal NE-SW strip (45°)": "شرائح قطرية شمال-شرق/جنوب-غرب (45°)",
    "Diagonal NW-SE strip (-45°)": "شرائح قطرية شمال-غرب/جنوب-شرق (-45°)",
    "Aligned with the longest edge": "بمحاذاة أطول ضلع",
}

# maps <-> map-recipe tooltips
MAP = {
    "land_boundary": ("Land boundary", "حدود الأرض"),
    "water": ("Water point", "مصدر الماء"),
    "basin": ("Basin", "حوض"),
    "basin_rec": ("Basin (recommended)", "الحوض (موصى به)"),
    "maxelev": ("Max elevation {z:.0f} m", "أقصى ارتفاع {z:.0f} م"),
    "sector": ("{name} - {area:,.0f} m\u00b2", "{name} - {area:,.0f} م\u00b2"),
    "zone": ("{name} - {area:,.0f} m\u00b2", "{name} - {area:,.0f} م\u00b2"),
    "principal": ("Principal pipe 90 mm", "الأنبوب الرئيسي 90 مم"),
    "major": ("Major 50 mm - {zone}", "فرعي رئيسي 50 مم - {zone}"),
    "minor": ("Minor 32 mm - {zone}", "فرعي 32 مم - {zone}"),
    "valve": ("{zone} - valve 50 mm", "{zone} - صمام 50 مم"),
}

# errors raised by parser/engine -> bilingual page message
ERRORS = {
    "No boundary polygon found in the upload.": "لم يُعثر على مضلع حدود في الملف.",
    "Point is outside the land boundary.": "النقطة خارج حدود الأرض.",
    "No water point found. Mark it in your file (KML Point or CSV row with type \"water\").":
        "لم يُعثر على مصدر ماء. ضع علامة عليه في ملفك (نقطة KML أو سطر CSV نوعه water).",
    "Boundary polygon is empty after projection.": "مضلع الحدود فارغ بعد الإسقاط.",
    "Unsupported file type (use .kml or .csv)": "نوع ملف غير مدعوم (استخدم .kml أو .csv)",
    "CSV must contain lon/lat columns (lon/lng/longitude/x and lat/latitude/y).":
        "يجب أن يحتوي CSV على عمودي خط الطول/العرض (lon/lng/longitude/x و lat/latitude/y).",
    "Empty CSV file": "ملف CSV فارغ",
    "Please choose a KML or CSV file first.": "يرجى اختيار ملف KML أو CSV أولاً.",
}


def esc(s):
    return html.escape(str(s), quote=False)


def config_ar(name):
    return CONFIG_NAMES.get(name, name)


def _ferr(en, ar):
    if not isinstance(en, (float, int)):
        return esc(en), esc(ar)
    return en, ar


# --------------------------------------------------------------------------- #
# Rendering helpers
# --------------------------------------------------------------------------- #
def markup(s):
    return Markup(s)


def bt(en, ar):
    """Bilingual text for a template element."""
    return Markup(
        '<span class="di"><span class="en">{0}</span>'
        '<span class="ar">{1}</span></span>'.format(esc(en), esc(ar))
    )


def btcfg(en):
    """Bilingual text for an engine-generated config name."""
    return bt(en, config_ar(en))


def t(key, **kw):
    en = EN[key].format(**kw)
    ar = AR.get(key, key).format(**kw)
    return bt(en, ar)


def tl(key):
    """Plain bilingual for Jinja (no wrapping spans) - rarely used."""
    return EN[key], AR.get(key, EN[key])


def nfmt(x, prec=0):
    return format(x, ",.{0}f".format(prec))


# --------------------------------------------------------------------------- #
# Standalone (map iframe) rendering - self-contained inline styles
# --------------------------------------------------------------------------- #
def bl_style(en, ar):
    return (
        '<span style="font-family:{ef};direction:ltr">{en}</span>'
        '<span style="font-family:{af};direction:rtl;unicode-bidi:embed">&nbsp;'
        '{ar}</span>'
    ).format(ef=EN_FONT, af=AR_FONT, en=esc(en), ar=esc(ar))


def map_tip(key, **kw):
    en, ar = MAP[key]
    try:
        en = en.format(**kw)
    except KeyError:
        pass
    try:
        ar = ar.format(**kw)
    except KeyError:
        pass
    return bl_style(en, ar)


def err(msg):
    """Translate a raised exception message into a bilingual error line."""
    ar = ERRORS.get(msg, msg)
    if ar == msg:
        # generic fallback: show the technical message bilingual-neutral
        return Markup('<span class="en">' + esc(msg) + "</span>")
    return bt(msg, ar)


def css():
    return (
        ".di { display: flex; justify-content: space-between; align-items: center;"
        " gap: 10px; flex-wrap: wrap; min-width: 0; }\n"
        ".di > .en { font-family: " + EN_FONT + "; direction: ltr; text-align: left; }\n"
        ".di > .ar, .ar { font-family: " + AR_FONT + "; direction: rtl; text-align: right; font-size: 16px; }\n"
        "body, .en { font-family: " + EN_FONT + "; }\n"
        "h1 .di > .ar, h2 .di > .ar, h3 .di > .ar, h4 .di > .ar, h5 .di > .ar { font-size: 20px; }\n"
        ".glass-head h1 .di > .ar, .glass-head h2 .di > .ar, .glass-head h3 .di > .ar,"
        " .glass-head h4 .di > .ar, .glass-head h5 .di > .ar { font-size: 18px; }\n"
        "button .di > .ar, a .di > .ar { font-size: 18px; }\n"
    )