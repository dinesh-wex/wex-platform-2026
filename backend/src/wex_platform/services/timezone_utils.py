"""Buyer timezone estimation — best-effort mapping from search city or phone area code."""

# City/state → IANA timezone mapping (top US warehouse markets)
CITY_TIMEZONE_MAP = {
    # Eastern
    "new york": "America/New_York",
    "newark": "America/New_York",
    "jersey city": "America/New_York",
    "philadelphia": "America/New_York",
    "atlanta": "America/New_York",
    "miami": "America/New_York",
    "fort lauderdale": "America/New_York",
    "orlando": "America/New_York",
    "tampa": "America/New_York",
    "jacksonville": "America/New_York",
    "charlotte": "America/New_York",
    "raleigh": "America/New_York",
    "richmond": "America/New_York",
    "baltimore": "America/New_York",
    "washington": "America/New_York",
    "boston": "America/New_York",
    "pittsburgh": "America/New_York",
    "columbus": "America/New_York",
    "cincinnati": "America/New_York",
    "cleveland": "America/New_York",
    "detroit": "America/New_York",
    "indianapolis": "America/New_York",
    # Central
    "chicago": "America/Chicago",
    "dallas": "America/Chicago",
    "fort worth": "America/Chicago",
    "houston": "America/Chicago",
    "san antonio": "America/Chicago",
    "austin": "America/Chicago",
    "nashville": "America/Chicago",
    "memphis": "America/Chicago",
    "minneapolis": "America/Chicago",
    "st louis": "America/Chicago",
    "kansas city": "America/Chicago",
    "milwaukee": "America/Chicago",
    "new orleans": "America/Chicago",
    "oklahoma city": "America/Chicago",
    "omaha": "America/Chicago",
    # Mountain
    "denver": "America/Denver",
    "salt lake city": "America/Denver",
    "albuquerque": "America/Denver",
    "el paso": "America/Denver",
    "boise": "America/Denver",
    "colorado springs": "America/Denver",
    # Arizona (no DST)
    "phoenix": "America/Phoenix",
    "tucson": "America/Phoenix",
    # Pacific
    "los angeles": "America/Los_Angeles",
    "san francisco": "America/Los_Angeles",
    "san jose": "America/Los_Angeles",
    "san diego": "America/Los_Angeles",
    "seattle": "America/Los_Angeles",
    "portland": "America/Los_Angeles",
    "sacramento": "America/Los_Angeles",
    "las vegas": "America/Los_Angeles",
    "oakland": "America/Los_Angeles",
    "riverside": "America/Los_Angeles",
    "stockton": "America/Los_Angeles",
    "fresno": "America/Los_Angeles",
    "long beach": "America/Los_Angeles",
}

# US area code → IANA timezone (major metro codes)
AREA_CODE_TIMEZONE_MAP = {
    # Eastern
    "201": "America/New_York",  # NJ
    "202": "America/New_York",  # DC
    "203": "America/New_York",  # CT
    "212": "America/New_York",  # NYC
    "215": "America/New_York",  # Philadelphia
    "216": "America/New_York",  # Cleveland
    "239": "America/New_York",  # FL (SW)
    "240": "America/New_York",  # MD
    "248": "America/New_York",  # MI (Detroit suburb)
    "267": "America/New_York",  # Philadelphia
    "301": "America/New_York",  # MD
    "302": "America/New_York",  # DE
    "305": "America/New_York",  # Miami
    "313": "America/New_York",  # Detroit
    "315": "America/New_York",  # NY (Syracuse)
    "317": "America/New_York",  # Indianapolis
    "321": "America/New_York",  # FL (Orlando)
    "330": "America/New_York",  # OH (Akron)
    "336": "America/New_York",  # NC
    "347": "America/New_York",  # NYC
    "352": "America/New_York",  # FL
    "386": "America/New_York",  # FL
    "401": "America/New_York",  # RI
    "404": "America/New_York",  # Atlanta
    "407": "America/New_York",  # Orlando
    "410": "America/New_York",  # Baltimore
    "412": "America/New_York",  # Pittsburgh
    "413": "America/New_York",  # MA (W)
    "443": "America/New_York",  # MD
    "470": "America/New_York",  # Atlanta
    "484": "America/New_York",  # PA
    "502": "America/New_York",  # Louisville
    "508": "America/New_York",  # MA
    "513": "America/New_York",  # Cincinnati
    "516": "America/New_York",  # NY (Long Island)
    "518": "America/New_York",  # NY (Albany)
    "551": "America/New_York",  # NJ
    "561": "America/New_York",  # FL (W Palm)
    "570": "America/New_York",  # PA
    "571": "America/New_York",  # VA (NoVA)
    "585": "America/New_York",  # NY (Rochester)
    "586": "America/New_York",  # MI
    "609": "America/New_York",  # NJ
    "610": "America/New_York",  # PA
    "614": "America/New_York",  # Columbus OH
    "617": "America/New_York",  # Boston
    "631": "America/New_York",  # NY (Long Island)
    "646": "America/New_York",  # NYC
    "678": "America/New_York",  # Atlanta
    "703": "America/New_York",  # VA (NoVA)
    "704": "America/New_York",  # Charlotte
    "706": "America/New_York",  # GA
    "716": "America/New_York",  # NY (Buffalo)
    "717": "America/New_York",  # PA
    "718": "America/New_York",  # NYC
    "727": "America/New_York",  # FL (Tampa)
    "732": "America/New_York",  # NJ
    "740": "America/New_York",  # OH
    "754": "America/New_York",  # FL (Ft Lauderdale)
    "757": "America/New_York",  # VA (Hampton Roads)
    "770": "America/New_York",  # GA (Atlanta suburb)
    "772": "America/New_York",  # FL
    "774": "America/New_York",  # MA
    "781": "America/New_York",  # MA (Boston suburb)
    "786": "America/New_York",  # Miami
    "804": "America/New_York",  # Richmond VA
    "813": "America/New_York",  # Tampa
    "828": "America/New_York",  # NC (Asheville)
    "845": "America/New_York",  # NY (Hudson Valley)
    "856": "America/New_York",  # NJ
    "860": "America/New_York",  # CT
    "862": "America/New_York",  # NJ
    "863": "America/New_York",  # FL
    "904": "America/New_York",  # Jacksonville
    "908": "America/New_York",  # NJ
    "910": "America/New_York",  # NC
    "914": "America/New_York",  # NY (Westchester)
    "917": "America/New_York",  # NYC
    "919": "America/New_York",  # Raleigh
    "929": "America/New_York",  # NYC
    "941": "America/New_York",  # FL (Sarasota)
    "954": "America/New_York",  # FL (Ft Lauderdale)
    "973": "America/New_York",  # NJ
    # Central
    "210": "America/Chicago",  # San Antonio
    "214": "America/Chicago",  # Dallas
    "217": "America/Chicago",  # IL (Springfield)
    "219": "America/Chicago",  # IN (NW)
    "224": "America/Chicago",  # IL (Chicago suburb)
    "225": "America/Chicago",  # Baton Rouge
    "228": "America/Chicago",  # MS
    "251": "America/Chicago",  # AL (Mobile)
    "254": "America/Chicago",  # TX (Waco)
    "256": "America/Chicago",  # AL (Huntsville)
    "262": "America/Chicago",  # WI
    "269": "America/Chicago",  # MI (SW - Central time)
    "281": "America/Chicago",  # Houston
    "312": "America/Chicago",  # Chicago
    "314": "America/Chicago",  # St Louis
    "316": "America/Chicago",  # Wichita
    "318": "America/Chicago",  # LA (Shreveport)
    "319": "America/Chicago",  # IA
    "320": "America/Chicago",  # MN
    "331": "America/Chicago",  # IL (Chicago suburb)
    "346": "America/Chicago",  # Houston
    "361": "America/Chicago",  # TX (Corpus Christi)
    "405": "America/Chicago",  # Oklahoma City
    "409": "America/Chicago",  # TX (Galveston)
    "414": "America/Chicago",  # Milwaukee
    "430": "America/Chicago",  # TX
    "432": "America/Chicago",  # TX (Midland)
    "469": "America/Chicago",  # Dallas
    "479": "America/Chicago",  # AR
    "501": "America/Chicago",  # Little Rock
    "504": "America/Chicago",  # New Orleans
    "507": "America/Chicago",  # MN
    "512": "America/Chicago",  # Austin
    "515": "America/Chicago",  # Des Moines
    "563": "America/Chicago",  # IA
    "573": "America/Chicago",  # MO
    "612": "America/Chicago",  # Minneapolis
    "615": "America/Chicago",  # Nashville
    "618": "America/Chicago",  # IL (S)
    "630": "America/Chicago",  # IL (Chicago suburb)
    "636": "America/Chicago",  # MO (St Louis suburb)
    "651": "America/Chicago",  # MN (St Paul)
    "682": "America/Chicago",  # TX (Fort Worth)
    "708": "America/Chicago",  # IL (Chicago suburb)
    "713": "America/Chicago",  # Houston
    "715": "America/Chicago",  # WI
    "737": "America/Chicago",  # Austin
    "763": "America/Chicago",  # MN
    "769": "America/Chicago",  # MS
    "773": "America/Chicago",  # Chicago
    "779": "America/Chicago",  # IL
    "806": "America/Chicago",  # TX (Lubbock)
    "815": "America/Chicago",  # IL
    "816": "America/Chicago",  # Kansas City
    "817": "America/Chicago",  # TX (Fort Worth)
    "830": "America/Chicago",  # TX
    "832": "America/Chicago",  # Houston
    "847": "America/Chicago",  # IL (Chicago suburb)
    "850": "America/Chicago",  # FL (Panhandle - Central)
    "870": "America/Chicago",  # AR
    "901": "America/Chicago",  # Memphis
    "913": "America/Chicago",  # KS (KC suburb)
    "918": "America/Chicago",  # Tulsa
    "920": "America/Chicago",  # WI
    "936": "America/Chicago",  # TX
    "940": "America/Chicago",  # TX
    "952": "America/Chicago",  # MN (Minneapolis suburb)
    "956": "America/Chicago",  # TX (Rio Grande)
    "972": "America/Chicago",  # Dallas
    "979": "America/Chicago",  # TX
    # Mountain
    "303": "America/Denver",  # Denver
    "307": "America/Denver",  # Wyoming
    "385": "America/Denver",  # Salt Lake City
    "406": "America/Denver",  # Montana
    "435": "America/Denver",  # UT
    "505": "America/Denver",  # Albuquerque
    "575": "America/Denver",  # NM
    "719": "America/Denver",  # CO (Colorado Springs)
    "720": "America/Denver",  # Denver
    "801": "America/Denver",  # Salt Lake City
    "915": "America/Denver",  # El Paso
    "970": "America/Denver",  # CO
    # Arizona (no DST)
    "480": "America/Phoenix",  # Phoenix (Scottsdale)
    "520": "America/Phoenix",  # Tucson
    "602": "America/Phoenix",  # Phoenix
    "623": "America/Phoenix",  # Phoenix (W)
    "928": "America/Phoenix",  # AZ (Flagstaff)
    # Pacific
    "206": "America/Los_Angeles",  # Seattle
    "209": "America/Los_Angeles",  # CA (Stockton)
    "213": "America/Los_Angeles",  # LA
    "253": "America/Los_Angeles",  # WA (Tacoma)
    "310": "America/Los_Angeles",  # LA (West)
    "323": "America/Los_Angeles",  # LA
    "360": "America/Los_Angeles",  # WA
    "408": "America/Los_Angeles",  # San Jose
    "415": "America/Los_Angeles",  # San Francisco
    "424": "America/Los_Angeles",  # LA
    "425": "America/Los_Angeles",  # WA (Bellevue)
    "442": "America/Los_Angeles",  # CA
    "503": "America/Los_Angeles",  # Portland
    "509": "America/Los_Angeles",  # WA (Spokane)
    "510": "America/Los_Angeles",  # Oakland
    "530": "America/Los_Angeles",  # CA (Sacramento N)
    "541": "America/Los_Angeles",  # OR
    "559": "America/Los_Angeles",  # CA (Fresno)
    "562": "America/Los_Angeles",  # Long Beach
    "619": "America/Los_Angeles",  # San Diego
    "626": "America/Los_Angeles",  # CA (Pasadena)
    "650": "America/Los_Angeles",  # CA (Peninsula)
    "657": "America/Los_Angeles",  # CA (Orange County)
    "661": "America/Los_Angeles",  # CA (Bakersfield)
    "669": "America/Los_Angeles",  # San Jose
    "702": "America/Los_Angeles",  # Las Vegas
    "707": "America/Los_Angeles",  # CA (Napa)
    "714": "America/Los_Angeles",  # CA (Orange County)
    "725": "America/Los_Angeles",  # Las Vegas
    "747": "America/Los_Angeles",  # CA (LA)
    "760": "America/Los_Angeles",  # CA
    "775": "America/Los_Angeles",  # NV (Reno)
    "805": "America/Los_Angeles",  # CA (Santa Barbara)
    "818": "America/Los_Angeles",  # CA (LA - Valley)
    "831": "America/Los_Angeles",  # CA (Monterey)
    "858": "America/Los_Angeles",  # San Diego
    "909": "America/Los_Angeles",  # CA (Inland Empire)
    "916": "America/Los_Angeles",  # Sacramento
    "925": "America/Los_Angeles",  # CA (East Bay)
    "949": "America/Los_Angeles",  # CA (Orange County)
    "951": "America/Los_Angeles",  # CA (Riverside)
    "971": "America/Los_Angeles",  # Portland
}


def get_buyer_timezone(state=None, *, phone: str | None = None, criteria: dict | None = None) -> str:
    """Best-effort timezone estimation: search city → area code → default ET.

    Can be called with an SMSConversationState object or with explicit phone/criteria.
    """
    # Signal 1: Search city from criteria
    _criteria = criteria or (getattr(state, "criteria_snapshot", None) if state else None) or {}
    city = (_criteria.get("city") or _criteria.get("location", "")).lower().strip()
    # Handle "city, state" format from location field
    if "," in city:
        city = city.split(",")[0].strip()
    if city and city in CITY_TIMEZONE_MAP:
        return CITY_TIMEZONE_MAP[city]

    # Signal 2: Phone area code
    _phone = phone or (getattr(state, "phone", None) if state else None) or ""
    _phone = _phone.replace("+1", "").replace("-", "").replace("(", "").replace(")", "").replace(" ", "").strip()
    if len(_phone) >= 10:
        area_code = _phone[:3] if not _phone.startswith("1") else _phone[1:4]
        if area_code in AREA_CODE_TIMEZONE_MAP:
            return AREA_CODE_TIMEZONE_MAP[area_code]

    # Last resort: default to Eastern
    return "America/New_York"
