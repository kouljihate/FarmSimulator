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
    # tabs
    "TAB_LOAD": "Load",
    "TAB_UPLOAD": "Upload",
    "TAB_BASIN": "Basin",
    "TAB_SECTORS": "Sectors",
    "TAB_ZONES": "Zones",
    "TAB_VALVE": "Valve",
    "TAB_PIPES": "Pipes",
    "TAB_OTHER": "Other Elements",
    "TAB_TREES": "Trees",
    "TAB_ROWS": "Rows",
    "TAB_RECAP": "Recap",
    "TAB_SIM": "Simulation",
    "TAB_FINAL": "Final Result",
    "ZONES_TITLE": "Zones",
    "ERROR_LABEL": "error",

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
    "MAJORS": "majors 63 mm",
    "MINORS": "minors 32 mm",
    "VALVE_PRINCIPAL": "Principal valve 90 mm",
    "VALVE_SECONDARY": "Secondary valve 32 mm",
    "VALVE_MGMT": "Valve management",
    "VALVE_MGMT_SUB": "Click the map to fill coordinates, pick a valve to move it, or add a new one.",
    "VALVE_TARGET": "Valve",
    "VALVE_NEW": "New valve",
    "VALVE_ADD": "Add valve",
    "VALVE_MOVE": "Save position",
    "VALVE_PICK": "Select a valve first.",
    "VALVE_DRAG_HINT": "Check sectors to focus them — drag valves, then Save. All (or none) checked shows the whole farm with instant saves.",
    "VALVE_SELECTED": "Selected valve",
    "VALVE_INFO_EMPTY": "Click a valve marker on the map (or Edit in the table) to see its details here.",
    "VALVE_SECTOR_FILTER": "Work on sectors",
    "VALVE_ALL_SECTORS": "All sectors",
    "VALVE_SHOW_ROWS": "Show rows",
    "VALVE_SAVE": "Save valves",
    "PIPE_SELECTED": "Selected pipe",
    "PIPE_INFO_EMPTY": "Click a pipe on the map (or Locate in the table) to see its details here.",
    "PIPE_CLICK_HINT": "Click a pipe to select it.",
    "LOCATE": "Locate",
    "PIPES": "Pipes",
    "PIPE_MGMT": "Pipe management",
    "PIPE_MGMT_SUB": "Trace start/end on the map or enter coordinates, pick a pipe to change it, or add a new one.",
    "PIPE_TARGET": "Pipe",
    "PIPE_NEW": "New pipe",
    "PIPE_TYPE": "Pipe type",
    "PIPE_CUSTOM": "Custom",
    "PIPE_ADD": "Add pipe",
    "PIPE_SAVE": "Save pipe",
    "PIPE_AI_TRACE": "AI Trace",
    "PIPE_AI_SUB": "AI orders the principal route and taps each pipe at the closest point.",
    "PIPE_SAVED": "Saved",
    "TREE_SUB": "Pick a tree type for each zone — zones can be mixed.",
    "TREE_SAVE": "Save trees",
    "TREE_DISTANCE": "Distance (m)",
    "TREE_PERCENT": "Area %",
    "TREE_PLANTED": "Planted",
    "TREE_COUNT": "Trees",
    "TREE_NONE": "None",
    "TREE_OLIVE": "Olive",
    "TREE_CITRUS": "Citrus",
    "TREE_ALMOND": "Almond",
    "TREE_POMEGRANATE": "Pomegranate",
    "TREE_APPLE": "Apple",
    "TREE_DATE_PALM": "Date palm",
    "TREE_GRAPE": "Grape",
    "TREE_FIG": "Fig",
    "ROWS_SUB": "AI traces crop rows along elevation contours for each zone — set the spacing and re-trace.",
    "ROW_SPACING": "Row spacing (m)",
    "ROW_TRACE": "Trace rows",
    "ROW_TREE": "Tree",
    "ROW_DIRECTION": "Direction",
    "ROW_SLOPE": "Slope",
    "ROW_ROWS": "Rows",
    "ROW_NEW_ANGLE": "New direction (°)",
    "RECAP_FILTER": "Layers",
    "RECAP_HINT": "Tick layers to display them. Tune color and size live on the map, then Save to keep.",
    "RECAP_SHOW": "Show",
    "RECAP_LAYER": "Layer",
    "RECAP_COLOR": "Color",
    "RECAP_SIZE": "Size",
    "RECAP_SAVE": "Save recap",
    "RECAP_LABELS": "Zone labels",
    "CONFIRM_ROWS": "Confirm Rows",
    "ROWS_CONFIRMED": "Rows confirmed",
    "ROWS_PENDING": "Rows pending confirmation",
    "ACTIONS": "Actions",
    "PRINCIPAL": "Principal",
    "SECONDARY": "Secondary",
    "KIND": "Type",
    "SECTOR": "Sector",
    "CONFIRM_ZONES": "Confirm Zones",
    "CONFIRM_VALVES": "Confirm Valves",
    "VALVES_CONFIRMED": "Valves confirmed",
    "VALVES_PENDING": "Valves pending confirmation",
    "ZONES_CONFIRMED": "Zones confirmed",
    "ZONES_PENDING": "Zones pending confirmation",
    "DELETE": "Delete",
    "DELETE_ASK": "Delete land {name}? All its data will be removed.",
    "EXPORT_PDF": "Export PDF",
    "REPORT_TITLE": "Land report",
    "OTHER_TITLE": "Other network elements",
    "OTHER_SUB": "Click the big map to fill coordinates, pick an element, then Add. Each element is AI-checked.",
    "OTHER_KIND": "Element",
    "OTHER_SIZE": "Size",
    "OTHER_ADD": "Add element",
    "OTHER_REMOVE": "Remove",
    "OTHER_EMPTY": "No extra elements yet.",
    "AI_VERDICT": "AI analysis",
    "AI_SUGGEST": "Cheaper / smoother proposal",
    "SIM_TITLE": "ROI Simulation",
    "SIM_SUB": "Estimate payback after X years. Tune the inputs, or use the AI proposal.",
    "SIM_YEARS": "Years",
    "SIM_CAPEX": "Initial investment",
    "SIM_COST": "Annual cost",
    "SIM_REVENUE": "Annual revenue",
    "SIM_CROP": "Crop",
    "SIM_RUN": "Simulate",
    "SIM_AI": "Use AI proposal",
    "SIM_BREAKEVEN": "Break-even year",
    "SIM_TOTAL": "Total net over period",
    "CURRENCY": "currency units",
    "ZONE_MGMT": "Zone management",
    "ZONE_SPLIT": "Manual Split",
    "ZONE_SPLIT_EQ": "Split Equivaly",
    "ZONE_TRACE_HINT": "Trace a line on the map or enter X/Y start and X/Y stop, then Split.",
    "ZONE_X1": "X start (lon)",
    "ZONE_Y1": "Y start (lat)",
    "ZONE_X2": "X stop (lon)",
    "ZONE_Y2": "Y stop (lat)",
    "ZONE_SPLIT_BTN": "Split",
    "ZONE_CLEAR_BTN": "Clear",
    "ZONE_CHANGE_BTN": "Change",
    "ZONE_RENAME": "Rename zone",
    "ZONE_SWAP": "Swap zones",
    "ZONE_MERGE": "Merge zones",
    "ZONE_REMOVE": "Remove zone",
    "ZONE_NAME_NEW": "New zone name",
    "TRACE_BTN": "Trace on map",
    "MAP_CLICK_HINT": "Click the map to fill coordinates.",

    # sector accordion
    "SECTOR_NAME": "Name",
    "CENTROID": "Centroid",
    "ENTRY_POINT": "Entry Point",
    "ZONE_ANGLE": "Zone Angle",
    "ZONES_COUNT": "Zones",

    # index
    "LOAD_TITLE": "Load a saved run",
    "LOAD": "Load",
    "SAVED_AT": "Last saved",
    "LOAD_EMPTY": "No saved runs yet - upload a file first, the maps and results are saved automatically.",
    "SECTOR_SELECT": "Select S{number}",
    "SECTOR_SELECT_MULTI": "Select one or more sectors S{number}",
    "MANAGE": "Manage",
    "SECTOR_ADD": "Add",
    "SECTOR_EDIT": "Edit",
    "SECTOR_RENAME": "Rename",
    "SECTOR_MERGE": "Merge",
    "SECTOR_SWAP": "Swap",
    "SECTOR_REMOVE": "Remove",
    "SELECT_HINT": "Select a sector to modify.",
    "SELECT_NEEDED": "Select a sector first.",
    "MERGE_PICK": "Now select the sector to merge with and press Merge.",
    "SWAP_NEED": "Check two sectors to swap.",
    "ZONE_ONE_NEED": "Select exactly one zone.",
    "ZONE_SWAP_NEED": "Check two zones to swap.",
    "ZONE_MERGE_NEED": "Check two or more zones to merge.",
    "DRAW_HINT": "Click on the map to draw the new sector, then press Done.",
    "EDIT_HINT": "Drag the yellow points, then press Done.",
    "FINISH": "Done",
    "CANCEL": "Cancel",
    "CANCEL_AR": "إلغاء",
    "CLOSE": "Close",
    "CLOSE_AR": "إغلاق",
    "CONFIRM": "Confirm",
    "CONFIRM_AR": "تأكيد",
    "NEW_NAME": "New sector name",
    "REMOVE_ASK": "Remove sector {name}? This action cannot be undone.",
    "SECTOR_NEEDS_NAME": "Sector",
    "SECTOR_RENAMED": "Sector renamed.",
    "SECTOR_NAME_TAKEN": "That sector name is already used. Pick a unique name.",
    "NETWORK_ERROR": "Request failed. Please try again.",
    "SAVING": "Saving...",
    "SAVED_OK": "Saved.",
    "LOADING": "Loading…",
    "SAVING": "Saving...",
    "MERGED_OK": "Sectors merged.",
    "REMOVED_OK": "Sector removed.",
    "ADDED_OK": "Sector added.",
    "EDITED_OK": "Sector updated.",
    "UPLOAD_TITLE": "1. Upload your land",
    "UPLOAD_CTRL_TEXT": "Choose a KML or CSV file from Google Maps (boundaries + water point).",
    "UPLOAD_BTN": "Analyse the plot",
    "UPLOAD_RESULT_TITLE": "Upload Result",
    "FILE_CONTENTS": "File contents",
    "EXTRA_POLYGONS": "Extra polygons",
    "WATER_POINTS": "Water points",
    "UPLOAD_FIRST": "Upload First a File (csv/kml)",
    "FORMATS_TITLE": "Accepted formats",
    "FMT_KML": "KML - the classic Google Maps \u201cMy Maps\u201d export. Every Polygon is a boundary; Point(s) are the water marks.",
    "FMT_CSV": "CSV - one row per vertex with a header, e.g. lat,lon,name,type. Rows whose type is water mark the source; everything else is a boundary ring.",
    "FMT_WKT": "WKT CSV - a geometry column with POLYGON(...) and POINT(...) rows.",
    "ELEV_NOTE": "Elevation is read from the KML altitude when present. Without it, the basin is placed at the most favourable point near the water entry.",
    "WHAT_TITLE": "What Part 1 produces",    "STEP_BASIN": "Basin - best spot near the water point at a favourable elevation.",
    "STEP_SECTORS": "Sectorisation - 3 config maps, every sector \u2264 10,000 m\u00b2, named S1, S2, \u2026",
    "STEP_ZONES": "Zonage - each sector splits into 3 equal zones Z1, Z2, Z3.",
    "STEP_VALVES": "Valves - one 90 mm principal valve per sector at its entry + one 32 mm secondary valve per zone at the sector/zone boundary intersection.",
    "STEP_PIPES": "Piping - 90 mm principal from the max elevation through the basin; 63 mm majors to each zone valve; 32 mm minors (P32-SxZy) along the zone boundary, perpendicular to the rows.",

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
    "BASIN_LIST": "Basins",
    "BASIN_ACTIVE_FORM": "Active basin - coordinates & name",
    "BASIN_ADD": "Add basin",
    "BASIN_ADD_SUB": "Adds an inactive basin; activate it to re-plan from there.",
    "BASIN_EDIT": "Edit",
    "BASIN_ACTIVATE": "Activate",
    "BASIN_ACTIVE": "Active",
    "BASIN_INACTIVE": "Inactive",
    "BASIN_NAME": "Name",
    "PIPE_DELETE_SEL": "Delete selected pipe",
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
    "LG_P50": "Major 63 mm",
    "LG_P32": "Minor 32 mm",
    "LG_VALVE": "Valve 50 mm",
    "LG_VALVE90": "Principal valve 90 mm",
    "LG_VALVE32": "Secondary valve 32 mm",
    "LG_OTHER": "Other element",

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
    "TAB_LOAD": "تحميل",
    "TAB_UPLOAD": "رفع",
    "TAB_BASIN": "الحوض",
    "TAB_SECTORS": "القطاعات",
    "TAB_ZONES": "المناطق",
    "TAB_VALVE": "الصمام",
    "TAB_PIPES": "الأنابيب",
    "TAB_OTHER": "عناصر أخرى",
    "TAB_TREES": "الأشجار",
    "TAB_ROWS": "الصفوف",
    "TAB_RECAP": "ملخص",
    "TAB_SIM": "محاكاة",
    "TAB_FINAL": "النتيجة النهائية",
    "ZONES_TITLE": "المناطق",
    "ERROR_LABEL": "خطأ",

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
    "MAJORS": "فرعيات رئيسية 63 مم",
    "MINORS": "فرعيات 32 مم",
    "VALVE_PRINCIPAL": "صمام رئيسي 90 مم",
    "VALVE_SECONDARY": "صمام ثانوي 32 مم",
    "VALVE_MGMT": "إدارة الصمامات",
    "VALVE_MGMT_SUB": "انقر على الخريطة لملء الإحداثيات، اختر صماماً لنقله، أو أضف صماماً جديداً.",
    "VALVE_TARGET": "الصمام",
    "VALVE_NEW": "صمام جديد",
    "VALVE_ADD": "إضافة صمام",
    "VALVE_MOVE": "حفظ الموقع",
    "VALVE_PICK": "اختر صماماً أولاً.",
    "VALVE_DRAG_HINT": "حدد القطاعات للتركيز عليها — اسحب الصمامات ثم احفظ. تحديد الكل (أو لا شيء) يعرض المزرعة كاملة مع حفظ فوري.",
    "VALVE_SELECTED": "الصمام المحدد",
    "VALVE_INFO_EMPTY": "انقر على علامة صمام في الخريطة (أو زر التعديل في الجدول) لعرض تفاصيله هنا.",
    "VALVE_SECTOR_FILTER": "العمل على القطاعات",
    "VALVE_ALL_SECTORS": "كل القطاعات",
    "VALVE_SHOW_ROWS": "عرض الصفوف",
    "VALVE_SAVE": "حفظ الصمامات",
    "PIPE_SELECTED": "الأنبوب المحدد",
    "PIPE_INFO_EMPTY": "انقر على أنبوب في الخريطة (أو زر التحديد في الجدول) لعرض تفاصيله هنا.",
    "PIPE_CLICK_HINT": "انقر على أنبوب لتحديده.",
    "LOCATE": "تحديد",
    "PIPES": "الأنابيب",
    "PIPE_MGMT": "إدارة الأنابيب",
    "PIPE_MGMT_SUB": "حدد البداية والنهاية على الخريطة أو أدخل الإحداثيات، اختر أنبوباً لتعديله، أو أضف أنبوباً جديداً.",
    "PIPE_TARGET": "الأنبوب",
    "PIPE_NEW": "أنبوب جديد",
    "PIPE_TYPE": "نوع الأنبوب",
    "PIPE_CUSTOM": "مخصص",
    "PIPE_ADD": "إضافة أنبوب",
    "PIPE_SAVE": "حفظ الأنبوب",
    "PIPE_AI_TRACE": "التتبع الذكي",
    "PIPE_AI_SUB": "يرتب الذكاء الاصطناعي مسار الأنبوب الرئيسي ويربط كل أنبوب بأقرب نقطة.",
    "PIPE_SAVED": "تم توفيره",
    "TREE_SUB": "اختر نوع الشجرة لكل منطقة — يمكن خلط الأنواع.",
    "TREE_SAVE": "حفظ الأشجار",
    "TREE_DISTANCE": "المسافة (م)",
    "TREE_PERCENT": "النسبة %",
    "TREE_PLANTED": "المزروع",
    "TREE_COUNT": "الأشجار",
    "TREE_NONE": "بدون",
    "TREE_OLIVE": "زيتون",
    "TREE_CITRUS": "حمضيات",
    "TREE_ALMOND": "لوز",
    "TREE_POMEGRANATE": "رمان",
    "TREE_APPLE": "تفاح",
    "TREE_DATE_PALM": "نخيل التمر",
    "TREE_GRAPE": "عنب",
    "TREE_FIG": "تين",
    "ROWS_SUB": "يخطط الذكاء الاصطناعي صفوف الزراعة على امتداد خطوط الارتفاع لكل منطقة — حدد التباعد وأعد التخطيط.",
    "ROW_SPACING": "التباعد بين الصفوف (م)",
    "ROW_TRACE": "تخطيط الصفوف",
    "ROW_TREE": "الشجرة",
    "ROW_DIRECTION": "الاتجاه",
    "ROW_SLOPE": "الانحدار",
    "ROW_ROWS": "الصفوف",
    "ROW_NEW_ANGLE": "اتجاه جديد (°)",
    "RECAP_FILTER": "الطبقات",
    "RECAP_HINT": "حدد الطبقات لعرضها. اضبط اللون والحجم مباشرة على الخريطة ثم احفظ.",
    "RECAP_SHOW": "عرض",
    "RECAP_LAYER": "الطبقة",
    "RECAP_COLOR": "اللون",
    "RECAP_SIZE": "الحجم",
    "RECAP_SAVE": "حفظ الملخص",
    "RECAP_LABELS": "تسميات المناطق",
    "CONFIRM_ROWS": "تأكيد الصفوف",
    "ROWS_CONFIRMED": "تم تأكيد الصفوف",
    "ROWS_PENDING": "بانتظار تأكيد الصفوف",
    "ACTIONS": "إجراءات",
    "PRINCIPAL": "رئيسي",
    "SECONDARY": "ثانوي",
    "KIND": "النوع",
    "SECTOR": "القطاع",
    "CONFIRM_ZONES": "تأكيد المناطق",
    "CONFIRM_VALVES": "تأكيد الصمامات",
    "VALVES_CONFIRMED": "تم تأكيد الصمامات",
    "VALVES_PENDING": "بانتظار تأكيد الصمامات",
    "ZONES_CONFIRMED": "تم تأكيد المناطق",
    "ZONES_PENDING": "بانتظار تأكيد المناطق",
    "DELETE": "حذف",
    "DELETE_ASK": "حذف الأرض {name}؟ سيتم حذف كل بياناتها.",
    "EXPORT_PDF": "تصدير PDF",
    "REPORT_TITLE": "تقرير الأرض",
    "OTHER_TITLE": "عناصر الشبكة الأخرى",
    "OTHER_SUB": "انقر على الخريطة الكبيرة لملء الإحداثيات، اختر عنصراً ثم أضف. كل عنصر يُحلَّل بالذكاء الاصطناعي.",
    "OTHER_KIND": "العنصر",
    "OTHER_SIZE": "الحجم",
    "OTHER_ADD": "إضافة عنصر",
    "OTHER_REMOVE": "إزالة",
    "OTHER_EMPTY": "لا عناصر إضافية بعد.",
    "AI_VERDICT": "تحليل ذكي",
    "AI_SUGGEST": "اقتراح أرخص وأسلس",
    "SIM_TITLE": "محاكاة العائد",
    "SIM_SUB": "قدّر العائد بعد X سنوات. عدّل المدخلات أو استخدم اقتراح الذكاء الاصطناعي.",
    "SIM_YEARS": "السنوات",
    "SIM_CAPEX": "الاستثمار الأولي",
    "SIM_COST": "التكلفة السنوية",
    "SIM_REVENUE": "الدخل السنوي",
    "SIM_CROP": "المحصول",
    "SIM_RUN": "محاكاة",
    "SIM_AI": "استخدام اقتراح الذكاء",
    "SIM_BREAKEVEN": "سنة التعادل",
    "SIM_TOTAL": "الصافي الإجمالي",
    "CURRENCY": "وحدة نقدية",
    "ZONE_MGMT": "إدارة المناطق",
    "ZONE_SPLIT": "تقسيم المنطقة بخط",
    "ZONE_SPLIT_EQ": "تقسيم متساوي",
    "ZONE_TRACE_HINT": "ارسم خطاً على الخريطة أو أدخل X/Y البداية والنهاية ثم قسّم.",
    "ZONE_X1": "X البداية (lon)",
    "ZONE_Y1": "Y البداية (lat)",
    "ZONE_X2": "X النهاية (lon)",
    "ZONE_Y2": "Y النهاية (lat)",
    "ZONE_SPLIT_BTN": "تقسيم",
    "ZONE_CLEAR_BTN": "مسح",
    "ZONE_CHANGE_BTN": "تغيير",
    "ZONE_RENAME": "تسمية المنطقة",
    "ZONE_SWAP": "تبديل المناطق",
    "ZONE_MERGE": "دمج المناطق",
    "ZONE_REMOVE": "حذف المنطقة",
    "ZONE_NAME_NEW": "اسم المنطقة الجديد",
    "TRACE_BTN": "رسم على الخريطة",
    "MAP_CLICK_HINT": "انقر على الخريطة لملء الإحداثيات.",

    # sector accordion
    "SECTOR_NAME": "الاسم",
    "CENTROID": "المركز",
    "ENTRY_POINT": "نقطة الدخول",
    "ZONE_ANGLE": "زاوية التقسيم",
    "SECTOR_SELECT": "حدد S{number}",
    "SECTOR_SELECT_MULTI": "حدد أكثر من منطقة S{number}",
    "ZONES_COUNT": "المناطق",

    "LOAD_TITLE": "تحميل نتيجة محفوظة",
    "LOAD": "تحميل",
    "SAVED_AT": "آخر حفظ",
    "LOAD_EMPTY": "لا توجد نتائج محفوظة بعد - ارفع ملفاً أولاً، وتُحفظ الخرائط والنتائج تلقائياً.",
    "SECTOR_SELECT": "تحديد القطاع",
    "SECTOR_SELECT_MULTI": "حدِّد قطاعاً أو أكثر",
    "MANAGE": "إدارة",
    "SECTOR_ADD": "إضافة",
    "SECTOR_EDIT": "تعديل",
    "SECTOR_RENAME": "تسمية",
    "SECTOR_MERGE": "دمج",
    "SECTOR_SWAP": "تبديل",
    "SECTOR_REMOVE": "حذف",
    "SELECT_HINT": "اختر قطاعاً لتعديله.",
    "SELECT_NEEDED": "اختر قطاعاً أولاً.",
    "MERGE_PICK": "اختر الآن القطاع المراد دمجه معه ثم اضغط دمج.",
    "SWAP_NEED": "حدد قطاعين للتبديل.",
    "ZONE_ONE_NEED": "حدد منطقة واحدة فقط.",
    "ZONE_SWAP_NEED": "حدد منطقتين للتبديل.",
    "ZONE_MERGE_NEED": "حدد منطقتين أو أكثر للدمج.",
    "DRAW_HINT": "انقر على الخريطة لرسم القطاع الجديد ثم اضغط تم.",
    "EDIT_HINT": "اسحب النقاط الصفراء ثم اضغط تم.",
    "FINISH": "تم",
    "CANCEL": "إلغاء",
    "CLOSE": "إغلاق",
    "CONFIRM": "تأكيد",
    "NEW_NAME": "اسم القطاع الجديد",
    "REMOVE_ASK": "حذف القطاع {name}؟ لا يمكن التراجع عن هذا الإجراء.",
    "SECTOR_NEEDS_NAME": "قطاع",
    "SECTOR_RENAMED": "تمت إعادة تسمية القطاع.",
    "SECTOR_NAME_TAKEN": "هذا الاسم مستخدم بالفعل. اختر اسماً فريداً.",
    "NETWORK_ERROR": "فشل الطلب. حاول مجدداً.",
    "SAVED_OK": "تم الحفظ.",
    "LOADING": "جارٍ التحميل…",
    "SAVING": "جارٍ الحفظ...",
    "MERGED_OK": "تم دمج القطاعات.",
    "REMOVED_OK": "تم حذف القطاع.",
    "ADDED_OK": "تمت إضافة القطاع.",
    "EDITED_OK": "تم تحديث القطاع.",
    "UPLOAD_TITLE": "1. رفع قطعة أرضك",
    "UPLOAD_CTRL_TEXT": "اختر ملف KML أو CSV من خرائط جوجل (الحدود + مصدر الماء).",
    "UPLOAD_BTN": "تحليل الأرض",
    "UPLOAD_RESULT_TITLE": "نتيجة الرفع",
    "FILE_CONTENTS": "محتويات الملف",
    "EXTRA_POLYGONS": "مضلعات إضافية",
    "WATER_POINTS": "مصادر الماء",
    "UPLOAD_FIRST": "ارفَع الملف أولاً (csv/kml)",
    "FORMATS_TITLE": "الصيغ المقبولة",
    "FMT_KML": "KML - التصدير الكلاسيكي من خرائط جوجل \u201cخرائطي\u201d. كل مضلع Polygon هو حدود، ونقاط Point هي علامات مصدر الماء.",
    "FMT_CSV": "CSV - سطر لكل رأس مع ترويسة مثل lat,lon,name,type. الأسطر التي نوعها water تميّز مصدر الماء، والباقي حلقات للحدود.",
    "FMT_WKT": "WKT CSV - عمود geometry يحتوي على POLYGON(...) و POINT(...).",
    "ELEV_NOTE": "يُقرأ الارتفاع من بيانات KML عند توفّره. بدونه، يُوضع الحوض في أفضل نقطة قرب مدخل الماء.",
    "WHAT_TITLE": "ماذا يُنتج الجزء الأول",
    "STEP_BASIN": "الحوض - أفضل موقع قرب مصدر الماء مع ارتفاع مناسب.",
    "STEP_SECTORS": "القطاعيات - 3 خرائط تخطيطات، كل قطاع \u2264 10,000 م\u00b2، وتسميته S1، S2، \u2026",
    "STEP_ZONES": "التقسيم - يُقسَّم كل قطاع إلى 3 مناطق متساوية Z1، Z2، Z3.",
    "STEP_VALVES": "الصمامات - صمام رئيسي 90 مم لكل قطاع عند مدخله + صمام ثانوي 32 مم لكل منطقة عند تقاطع حدود القطاع والمنطقة.",
    "STEP_PIPES": "الأنابيب - رئيسي 90 مم من أعلى ارتفاع عبر الحوض؛ فرعيات رئيسية 63 مم إلى كل صمام منطقة؛ فرعيات 32 مم (P32-SxZy) على حدود المنطقة، عمودية على الصفوف.",

    "BASIN_TITLE": "موقع الحوض",
    "BASIN_REC": "الحوض الموصى به عند",
    "DIST_WATER": "المسافة من مصدر الماء",
    "ELEVATION": "الارتفاع",
    "MAX_ELEV_IN": "أقصى ارتفاع داخل الأرض",
    "APPLY": "تطبيق",
    "LON": "X / خط الطول",
    "LAT": "Y / خط العرض",
    "DRAG_HINT": "اسحب العلامة البنية على الخريطة، أو عدّل الإحداثيات ثم اضغط تطبيق، لتغيير موقع الحوض.",
    "BASIN_LIST": "الأحواض",
    "BASIN_ACTIVE_FORM": "الحوض النشط - الإحداثيات والاسم",
    "BASIN_ADD": "إضافة حوض",
    "BASIN_ADD_SUB": "يضيف حوضًا غير نشط؛ فعّله لإعادة التخطيط منه.",
    "BASIN_EDIT": "تعديل",
    "BASIN_ACTIVATE": "تفعيل",
    "BASIN_ACTIVE": "نشط",
    "BASIN_INACTIVE": "غير نشط",
    "BASIN_NAME": "الاسم",
    "PIPE_DELETE_SEL": "حذف الخط المحدد",
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
    "LG_P50": "فرعي رئيسي 63 مم",
    "LG_P32": "فرعي 32 مم",
    "LG_VALVE": "صمام 50 مم",
    "LG_VALVE90": "صمام رئيسي 90 مم",
    "LG_VALVE32": "صمام ثانوي 32 مم",
    "LG_OTHER": "عنصر آخر",

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
    "Balanced grid": "شبكة متوازنة",
    "Mosaic (mixed cell sizes)": "فسيفساء (خلايا بأحجام مختلفة)",
    "Fine (smaller cells)": "دقيق (خلايا أصغر)",
    "Existing sectors": "قطاعات موجودة",
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
    "major63": ("Major 63 mm - {zone}", "فرعي رئيسي 63 مم - {zone}"),
    "minor": ("Minor 32 mm - {zone}", "فرعي 32 مم - {zone}"),
    "valve": ("{zone} - valve 50 mm", "{zone} - صمام 50 مم"),
    "valve90": ("{zone} - principal valve 90 mm", "{zone} - صمام رئيسي 90 مم"),
    "valve32": ("{zone} - secondary valve 32 mm", "{zone} - صمام ثانوي 32 مم"),
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
    "Sector not found.": "القطاع غير موجود.",
    "Valve not found.": "الصمام غير موجود.",
    "Pipe not found.": "الأنبوب غير موجود.",
    "Invalid tree selection.": "اختيار شجرة غير صالح.",
    "Invalid tree spacing.": "تباعد أشجار غير صالح.",
    "Invalid tree percentage.": "نسبة أشجار غير صالحة.",
    "Invalid spacing.": "تباعد غير صالح.",
    "Invalid angle.": "زاوية غير صالحة.",
    "Invalid layers.": "طبقات غير صالحة.",
    "Cannot remove the principal pipe.": "لا يمكن حذف الأنبوب الرئيسي.",
    "Nothing to change.": "لا شيء لتغييره.",
    "The pipe must lie inside the land boundary.": "يجب أن يكون الأنبوب داخل حدود الأرض.",
    "Invalid diameter.": "قطر غير صالح.",
    "Zone not found.": "المنطقة غير موجودة.",
    "Empty sector name.": "اسم القطاع فارغ.",
    "Empty zone name.": "اسم المنطقة فارغ.",
    "That sector name is already used. Pick a unique name.": "هذا الاسم مستخدم بالفعل. اختر اسماً فريداً.",
    "That zone name is already used. Pick a unique name.": "اسم المنطقة مستخدم بالفعل. اختر اسماً فريداً.",
    "Cannot remove the last sector.": "لا يمكن حذف القطاع الأخير.",
    "Cannot remove the last zone.": "لا يمكن حذف المنطقة الأخيرة.",
    "The line must cross the zone.": "يجب أن يعبر الخط المنطقة.",
    "Select two sectors to merge.": "اختر قطاعين للدمج.",
    "Select two sectors to swap.": "اختر قطاعين للتبديل.",
    "Select two zones to swap.": "اختر منطقتين للتبديل.",
    "Select two zones to merge.": "اختر منطقتين أو أكثر للدمج.",
    "Merge produced an empty sector.": "نتج عن الدمج قطاع فارغ.",
    "Invalid polygon.": "مضلع غير صالح.",
    "Invalid coordinates.": "إحداثيات غير صالحة.",
    "Sector is too small (minimum ~60 m2).": "القطاع صغير جداً (الحد الأدنى ~60 م²).",
    "The sector must lie inside the land boundary.": "يجب أن يكون القطاع داخل حدود الأرض.",
    "The valve must lie inside the land boundary.": "يجب أن يكون الصمام داخل حدود الأرض.",
    "Unknown operation.": "عملية غير معروفة.",
    "Basin not found.": "الحوض غير موجود.",
    "Cannot remove the active basin. Activate another basin first.":
        "لا يمكن حذف الحوض النشط. فعّل حوضًا آخر أولاً.",
}


def esc(s):
    return html.escape(str(s), quote=False)


def config_ar(name):
    for suffix, ar_suffix in ((" cells)", " خلايا)"), (" polygons)", " مضلّعات)")):
        if name.endswith(suffix):
            base, sep, count = name[:-(len(suffix))].rpartition(" (")
            if sep and count.isdigit():
                return "{0} ({1}{2}".format(config_ar(base), count, ar_suffix)
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


def bi(key):
    """Inline bilingual text (no flex wrapper) for centred or inline spots."""
    en = EN[key]
    ar = AR.get(key, en)
    return Markup(
        '<span class="en">{en}</span> <span class="ar">{ar}</span>'.format(
            en=esc(en), ar=esc(ar))
    )


def btcfg(en):
    """Bilingual text for an engine-generated config name."""
    return bt(en, config_ar(en))


def bv(key):
    """Vertical bilingual for compact buttons: Arabic on top, English below."""
    en = EN[key]
    ar = AR.get(key, en)
    return Markup(
        '<span class="bv"><span class="ar">{ar}</span>'
        '<span class="en">{en}</span></span>'.format(en=esc(en), ar=esc(ar))
    )


def bvfmt(key, **kw):
    """Vertical bilingual with .format() applied (AR on top, EN below)."""
    en = EN[key].format(**kw)
    ar = AR.get(key, EN[key]).format(**kw)
    return Markup(
        '<span class="bv"><span class="ar">{ar}</span>'
        '<span class="en">{en}</span></span>'.format(en=esc(en), ar=esc(ar))
    )


def ts(key):
    """Plain (no markup) bilingual line for JS-set status text."""
    en = EN[key]
    ar = AR.get(key, en)
    return "{en} | {ar}".format(en=esc(en), ar=esc(ar))


def tsf(key, **kw):
    """ts(key) with .format() applied (e.g. {name} -> sector name)."""
    en = EN[key].format(**kw)
    ar = AR.get(key, EN[key]).format(**kw)
    return "{en} | {ar}".format(en=esc(en), ar=esc(ar))


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