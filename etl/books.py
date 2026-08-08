"""Canonical book table.

Book codes are USFM/Paratext 3-letter codes (GEN, PHP, MRK ...) because that is
what Nave's Topical Bible already uses for its references and what the app's
"call number" reference format is built on: BOK.C.V -> PHP.4.6
"""

# (code, display name, alternate names found in source datasets)
BOOKS = [
    ("GEN", "Genesis", []),
    ("EXO", "Exodus", []),
    ("LEV", "Leviticus", []),
    ("NUM", "Numbers", []),
    ("DEU", "Deuteronomy", []),
    ("JOS", "Joshua", []),
    ("JDG", "Judges", []),
    ("RUT", "Ruth", []),
    ("1SA", "1 Samuel", ["I Samuel", "First Samuel", "1Samuel"]),
    ("2SA", "2 Samuel", ["II Samuel", "Second Samuel", "2Samuel"]),
    ("1KI", "1 Kings", ["I Kings", "First Kings", "1Kings"]),
    ("2KI", "2 Kings", ["II Kings", "Second Kings", "2Kings"]),
    ("1CH", "1 Chronicles", ["I Chronicles", "First Chronicles", "1Chronicles"]),
    ("2CH", "2 Chronicles", ["II Chronicles", "Second Chronicles", "2Chronicles"]),
    ("EZR", "Ezra", []),
    ("NEH", "Nehemiah", []),
    ("EST", "Esther", []),
    ("JOB", "Job", []),
    ("PSA", "Psalms", ["Psalm"]),
    ("PRO", "Proverbs", []),
    ("ECC", "Ecclesiastes", []),
    ("SNG", "Song of Solomon", ["Song of Songs", "Canticles"]),
    ("ISA", "Isaiah", []),
    ("JER", "Jeremiah", []),
    ("LAM", "Lamentations", []),
    ("EZK", "Ezekiel", []),
    ("DAN", "Daniel", []),
    ("HOS", "Hosea", []),
    ("JOL", "Joel", []),
    ("AMO", "Amos", []),
    ("OBA", "Obadiah", []),
    ("JON", "Jonah", []),
    ("MIC", "Micah", []),
    ("NAM", "Nahum", []),
    ("HAB", "Habakkuk", []),
    ("ZEP", "Zephaniah", []),
    ("HAG", "Haggai", []),
    ("ZEC", "Zechariah", []),
    ("MAL", "Malachi", []),
    ("MAT", "Matthew", []),
    ("MRK", "Mark", []),
    ("LUK", "Luke", []),
    ("JHN", "John", []),
    ("ACT", "Acts", ["Acts of the Apostles"]),
    ("ROM", "Romans", []),
    ("1CO", "1 Corinthians", ["I Corinthians", "First Corinthians"]),
    ("2CO", "2 Corinthians", ["II Corinthians", "Second Corinthians"]),
    ("GAL", "Galatians", []),
    ("EPH", "Ephesians", []),
    ("PHP", "Philippians", []),
    ("COL", "Colossians", []),
    ("1TH", "1 Thessalonians", ["I Thessalonians", "First Thessalonians"]),
    ("2TH", "2 Thessalonians", ["II Thessalonians", "Second Thessalonians"]),
    ("1TI", "1 Timothy", ["I Timothy", "First Timothy"]),
    ("2TI", "2 Timothy", ["II Timothy", "Second Timothy"]),
    ("TIT", "Titus", []),
    ("PHM", "Philemon", []),
    ("HEB", "Hebrews", []),
    ("JAS", "James", []),
    ("1PE", "1 Peter", ["I Peter", "First Peter"]),
    ("2PE", "2 Peter", ["II Peter", "Second Peter"]),
    ("1JN", "1 John", ["I John", "First John", "1Jhn"]),
    ("2JN", "2 John", ["II John", "Second John"]),
    ("3JN", "3 John", ["III John", "Third John"]),
    ("JUD", "Jude", []),
    ("REV", "Revelation", ["Revelation of John", "The Revelation"]),
]

CODES = [b[0] for b in BOOKS]
ORDINAL = {code: i + 1 for i, code in enumerate(CODES)}
NAME = {code: name for code, name, _ in BOOKS}
OT_END = ORDINAL["MAL"]


def testament(code: str) -> str:
    return "OT" if ORDINAL[code] <= OT_END else "NT"


def _norm(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())


# name (and alias) -> code, for datasets that spell books out
_BY_NAME = {}
for _code, _name, _aliases in BOOKS:
    _BY_NAME[_norm(_name)] = _code
    for _a in _aliases:
        _BY_NAME[_norm(_a)] = _code

# Codes seen in source data that differ from the canonical set.
_CODE_FIXUPS = {
    "1JHN": "1JN",
    "2JHN": "2JN",
    "3JHN": "3JN",
    "SOL": "SNG",
    "SOS": "SNG",
    "SON": "SNG",
    "MAR": "MRK",
    "PHI": "PHP",
    "JOH": "JHN",
    "EZE": "EZK",
    "JOE": "JOL",
    "NAH": "NAM",
    "JUDG": "JDG",
    "PSM": "PSA",
}


def resolve(token: str):
    """Map a book code or spelled-out book name to a canonical code."""
    t = token.strip()
    upper = t.upper().replace(".", "")
    if upper in ORDINAL:
        return upper
    if upper in _CODE_FIXUPS:
        return _CODE_FIXUPS[upper]
    return _BY_NAME.get(_norm(t))
