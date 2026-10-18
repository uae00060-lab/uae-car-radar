"""What the seller says about the car itself: regional specs and warning signs.

Read only from the ad's own fields, title and description. A sign counts only when the text states
it plainly; "no accidents", "accident free" or "بدون حوادث" never raise a flag.
"""

import re

SPEC_AR = {"gcc": "خليجي", "american": "وارد أمريكا", "canadian": "وارد كندا", "japanese": "وارد اليابان",
           "european": "وارد أوروبا", "korean": "وارد كوريا", "chinese": "وارد الصين", "other": "وارد"}

# Most specific first: "GCC" inside "Non-GCC" must not read as GCC.
SPEC_PATTERNS = (
    ("other", r"\bnon[\s-]*gcc\b|غير\s*خليجي|مش\s*خليجي|ليست?\s*خليجي"),
    ("american", r"\b(?:american|us|usa|u\.s\.?)\s*(?:spec|specs|specification|import(?:ed)?)\b|"
                 r"\bimport(?:ed)?\s*(?:from\s*)?(?:the\s*)?(?:usa?|america)\b|"
                 r"(?:مواصفات|وارد|استيراد)\s*(?:ال)?(?:أ|ا)مري?كي?[ةه]?|(?:أ|ا)مريكي\s*(?:المواصفات|مواصفات)"),
    ("canadian", r"\bcanad(?:a|ian)\s*(?:spec|specs|import(?:ed)?)\b|(?:مواصفات|وارد)\s*كند(?:ا|ي[ةه]?)"),
    ("japanese", r"\bjapan(?:ese)?\s*(?:spec|specs|import(?:ed)?)\b|(?:مواصفات|وارد)\s*(?:ال)?يابان(?:ي[ةه]?)?"),
    ("european", r"\beuro(?:pean)?\s*(?:spec|specs|import(?:ed)?)\b|(?:مواصفات|وارد)\s*(?:ال)?(?:أ|ا)وروب(?:ا|ي[ةه]?)"),
    ("korean", r"\bkorea(?:n)?\s*(?:spec|specs|import(?:ed)?)\b|(?:مواصفات|وارد)\s*كور(?:يا|ي[ةه]?)"),
    ("chinese", r"\bchin(?:a|ese)\s*(?:spec|specs|import(?:ed)?)\b|(?:مواصفات|وارد)\s*(?:ال)?صين(?:ي[ةه]?)?"),
    ("gcc", r"\bgcc\b|\bg\.c\.c\b|خليجي[ةه]?|مواصفات\s*(?:ال)?خليج"),
)
SPEC_FIELD = {"gcc": "gcc", "gulf": "gcc", "خليجي": "gcc", "خليجية": "gcc", "خليجيه": "gcc",
              "american": "american", "us": "american", "usa": "american", "أمريكي": "american", "امريكي": "american",
              "أمريكية": "american", "امريكية": "american", "canadian": "canadian", "كندي": "canadian",
              "japanese": "japanese", "ياباني": "japanese", "يابانية": "japanese", "european": "european",
              "أوروبي": "european", "اوروبي": "european", "korean": "korean", "كوري": "korean", "chinese": "chinese",
              "صيني": "chinese"}


def spec_of(field, text=""):
    """'gcc', an import origin, 'other', or None when the ad does not say."""
    value = re.sub(r"\s*specs?$", "", str(field or "").strip().lower())
    if value in SPEC_FIELD:
        return SPEC_FIELD[value]
    if value:
        for spec, rx in SPEC_PATTERNS:
            if re.search(rx, value, re.I):
                return spec
        return "other"  # a regional spec named by the platform, outside the usual ones
    for spec, rx in SPEC_PATTERNS:
        if re.search(rx, str(text or ""), re.I):
            return spec
    return None


FLAG_AR = {"accident": "حادث سابق", "flood": "غرق", "salvage": "سالفج / شطب تأمين", "export": "معروضة للتصدير",
           "registration": "مشكلة تسجيل أو ملكية", "repaint": "رش / صبغ", "mechanical": "عطل ميكانيكي",
           "airbag": "الوسائد الهوائية انفتحت"}

FLAG_PATTERNS = {
    "accident": r"\baccident(?:ed|s)?\b|\b(?:front|rear|side|minor|major)\s*(?:damage|hit)\b|\bdamaged\b|"
                r"\bمصدوم[ةه]?\b|\bحادث\b|\bحوادث\b|\bتصادم\b|\bضرب[ةه]\b",
    "flood": r"\bflood(?:ed)?\b|\bwater\s*damage[d]?\b|غرق|غرقان[ةه]?|مغرق[ةه]?",
    "salvage": r"\bsalvage[d]?\b|\brebuilt\s*title\b|\btotal\s*loss\b|\bwrite[\s-]*off\b|\bwritten\s*off\b|سالفج|سالفيج|شطب",
    "export": r"\bexport\s*only\b|\bfor\s*export\b|للتصدير|تصدير\s*فقط",
    "registration": r"\bnot\s*registered\b|\bno\s*registration\b|\bregistration\s*expired\b|\bwithout\s*(?:registration|mulkiya)\b|"
                    r"بدون\s*(?:ملكي[ةه]|تسجيل)|(?:الملكي[ةه]|التسجيل)\s*منتهي[ةه]?|غير\s*مسجل[ةه]?",
    "repaint": r"\brepaint(?:ed)?\b|\bpainted\b|\bre[\s-]*sprayed\b|\bمرشوش[ةه]?\b|\bرش\b|\bمصبوغ[ةه]?\b|\bصبغ(?:[ةه]|ات)?\b|\bبوي[ةه]\b|\bدهان\b",
    "mechanical": r"\b(?:engine|gear\s*box|gearbox|transmission|gear)\s*(?:problem|issue|fault|needs?\s*(?:repair|work)|not\s*working)\b|"
                  r"\bneeds?\s*(?:engine|gearbox|transmission)\b|"
                  r"(?:عطل|خراب|مشكل[ةه]|مشاكل)\s*(?:في\s*)?(?:ال)?(?:مكين[ةه]|محرك|جير|قير)|(?:ال)?(?:مكين[ةه]|جير|قير)\s*(?:خربان|عطلان|فيه[اـ]?\s*مشكل[ةه])",
    "airbag": r"\bairbags?\s*(?:deployed|opened|open)\b|(?:ال)?(?:ايرباج|إيرباج|ايرباق|وسائد\s*هوائي[ةه])\s*(?:مفتوح[ةه]?|انفتح[ت]?|طالع[ةه]?)",
}

# A flag word preceded by one of these (within a few words) is a denial, not a warning.
NEGATION = re.compile(
    r"(?:\bno\b|\bnot\b|\bnever\b|\bzero\b|\bnothing\b|\bwithout\b|\bnil\b|\bnone\b|\b0\b|\bfree\s*(?:of|from)\b|\bclean\b|\bnot\s*any\b|"
    r"بدون|بلا|ولا|لا\s*يوجد|لايوجد|ما\s*في(?:ها)?|مافي(?:ها)?|ليس|ليست|غير|خالي[ةه]?\s*من|خال\s*من|نظيف[ةه]?\s*من|"
    r"صفر|لم\s*تتعرض|ما\s*تعرضت|ماتعرضت|ما\s*عليها|ماعليها|مو)\W*(?:\w+\W+){0,3}$", re.I)
# Words after the flag that deny or neutralise it: "accident free", "صبغ وكالة", "original paint".
AFTER = re.compile(r"^\W*(?:free\b|[-\s]*free\b|history\s*:\s*(?:no|none|clean)\b|report\s*:\s*clean\b|:\s*(?:no|none|0)\b|"
                   r"وكال[ةه]|الوكال[ةه]|أصلي|اصلي|لا\b|:\s*لا\b|0\b|صفر)", re.I)
# Phrases that are about something else: a road accident cover, a free check, a clean-title promise.
IGNORE = re.compile(r"accident\s*(?:cover|insurance|replacement|assistance)|ضد\s*(?:ال)?حوادث|"
                    r"accident\s*(?:&|and|/)?\s*(?:\w+\s*)?(?:check|history\s*check)|"
                    r"export\s*(?:and|&|or|/)\s*local|local\s*(?:and|&|or|/)\s*export|"
                    r"(?:ال)?محلي\s*(?:و|أو|او)\s*(?:ال)?تصدير|(?:ال)?تصدير\s*(?:و|أو|او)\s*(?:ال)?محلي|"
                    r"\bpaint\s*protection\b|ppf|نانو|سيراميك|حماي[ةه]\s*(?:ال)?(?:صبغ|طلاء)", re.I)


def red_flags(text):
    """[{'kind', 'label', 'word'}] for warning signs the seller states, at most one per kind."""
    text = re.sub(r"\s+", " ", str(text or ""))
    flags = []
    for kind, rx in FLAG_PATTERNS.items():
        for m in re.finditer(rx, text, re.I):
            # Only the same clause can deny it: "No accidents, repainted" still says repainted.
            before = re.split(r"[.,،؛;!?\n|/•*()\[\]-]", text[max(0, m.start() - 40): m.start()])[-1]
            after = text[m.end(): m.end() + 25]
            around = text[max(0, m.start() - 25): m.end() + 25]
            if NEGATION.search(before) or AFTER.search(after) or IGNORE.search(around):
                continue
            flags.append({"kind": kind, "label": FLAG_AR[kind], "word": m[0].strip()[:30]})
            break
    return flags
