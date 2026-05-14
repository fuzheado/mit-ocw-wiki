#!/usr/bin/env python3
"""Classify all 942 WikiProjects into domains for the Contribution Impact Matrix.

Taxonomy
--------
Derived from Wikipedia's Vital Articles Level 4/5 hierarchy (the community-
vetted system for organizing the 10,000/50,000 most important articles), then
modified with pragmatic elevation: topics with high WikiProject volume or high
user discoverability expectations are promoted to top-level categories even
when the strict hierarchy would bury them.

Design rationale documented in:
    notes/scalability-and-domain-classification.md

Usage:
    python3 scripts/classify_projects.py
"""

import sys
import re
import json
sys.path.insert(0, 'scripts')
from wiki_cache import WIKI_UA
from urllib.request import Request, urlopen
from urllib.parse import quote, unquote


def fetch_project_names():
    """Fetch all WikiProjects with Popular pages from the Community Tech bot page.

    Source: https://en.wikipedia.org/wiki/User:Community_Tech_bot/Popular_pages
    This is the authoritative list — 942 projects total.
    """
    page = 'User:Community_Tech_bot/Popular_pages'
    url = (
        f"https://en.wikipedia.org/w/api.php"
        f"?action=parse&page={quote(page)}&prop=text&format=json"
    )
    req = Request(url, headers={'User-Agent': WIKI_UA})
    data = json.loads(urlopen(req, timeout=15).read())
    html = data['parse']['text']['*']
    links = re.findall(
        r'<a[^>]*href="/wiki/Wikipedia:WikiProject_([^"]+)/Popular_pages"[^>]*>', html
    )
    return sorted(set(unquote(l.replace('_', ' ')) for l in links))


def wb(word):
    """Return a word-boundary regex for exact whole-word matching."""
    return r'(?<![a-zA-Z])' + re.escape(word) + r'(?![a-zA-Z])'


def classify_domain(name):
    """Classify a WikiProject name into a domain category.

    Rules are evaluated in priority order — first match wins.
    Each rule specifies: (domain, keywords, exclude_if_contains).
    Keywords and excludes use whole-word matching (word boundaries).
    """
    lower = name.lower()

    rules = [

        # ── 1. Geography & Places ──────────────────────────────────────
        # Evaluated first because countries/states/cities are the most
        # numerous group (265) and their names can collide with other
        # domains. Exclusions block history/science terms that happen
        # to contain country names (e.g., "Ancient Egypt", "Roman Empire").
        ("Geography & Places", [
            "afghanistan", "aland", "albania", "algeria", "andorra", "angola",
            "antigua and barbuda", "argentina", "armenia", "australia", "austria",
            "azerbaijan", "bahrain", "bangladesh", "barbados", "belarus",
            "belgium", "belize", "benin", "bhutan", "bolivia", "bosnia and herzegovina",
            "botswana", "brazil", "brunei", "bulgaria", "burkina", "burma",
            "burundi", "cambodia", "cameroon", "canada", "cape verde", "chad",
            "chile", "china", "colombia", "comoros", "congo", "cook islands",
            "costa rica", "croatia", "cuba", "cyprus", "czech republic",
            "denmark", "djibouti", "dominica", "dominican republic",
            "east timor", "ecuador", "egypt", "el salvador", "england",
            "equatorial guinea", "eritrea", "estonia", "eswatini", "ethiopia",
            "faroe islands", "fiji", "finland", "france", "gabon", "gambia",
            "georgia (u.s. state)", "germany", "ghana", "greece", "grenada",
            "guatemala", "guinea", "guinea-bissau", "guyana", "haiti",
            "honduras", "hong kong", "hungary", "iceland", "india", "indonesia",
            "iran", "iraq", "ireland", "israel", "italy", "ivory coast",
            "jamaica", "japan", "jordan", "kazakhstan", "kenya", "kiribati",
            "korea", "kosovo", "kuwait", "kyrgyzstan", "laos", "latvia",
            "lebanon", "lesotho", "liberia", "libya", "liechtenstein",
            "lithuania", "luxembourg", "macau", "madagascar", "malawi",
            "malaysia", "maldives", "mali", "malta", "marshall islands",
            "mauritania", "mauritius", "mexico", "micronesia", "moldova",
            "monaco", "mongolia", "montenegro", "morocco", "mozambique",
            "myanmar", "namibia", "nauru", "nepal", "netherlands",
            "new zealand", "nicaragua", "niger", "nigeria", "north korea",
            "north macedonia", "norway", "oman", "pakistan", "palau",
            "palestine", "panama", "papua new guinea", "paraguay", "peru",
            "philippines", "poland", "portugal", "qatar", "romania", "russia",
            "rwanda", "saint kitts and nevis", "saint lucia",
            "saint vincent and the grenadines", "samoa", "san marino",
            "sao tome and principe", "saudi arabia", "scotland", "senegal",
            "serbia", "seychelles", "sierra leone", "singapore", "slovakia",
            "slovenia", "solomon islands", "somalia", "south africa",
            "south korea", "south sudan", "spain", "sri lanka", "sudan",
            "suriname", "sweden", "switzerland", "syria", "taiwan",
            "tajikistan", "tanzania", "thailand", "timor-leste", "togo",
            "tonga", "trinidad and tobago", "tunisia", "turkey",
            "turkmenistan", "tuvalu", "uganda", "ukraine",
            "united arab emirates", "united kingdom", "united states", "uruguay",
            "uzbekistan", "vanuatu", "vatican", "venezuela", "vietnam",
            "wales", "yemen", "zambia", "zimbabwe",
            # US States
            "alabama", "alaska", "arizona", "arkansas", "california",
            "colorado", "connecticut", "delaware", "florida",
            "georgia (u.s. state)", "hawaii", "idaho", "illinois",
            "indiana", "iowa", "kansas", "kentucky", "louisiana", "maine",
            "maryland", "massachusetts", "michigan", "minnesota",
            "mississippi", "missouri", "montana", "nebraska", "nevada",
            "new hampshire", "new jersey", "new mexico", "new york",
            "north carolina", "north dakota", "ohio", "oklahoma", "oregon",
            "pennsylvania", "rhode island", "south carolina", "south dakota",
            "tennessee", "texas", "utah", "vermont", "virginia",
            "washington", "west virginia", "wisconsin", "wyoming",
            # Cities / regions
            "adelaide", "bendigo", "boston", "bristol", "chicago",
            "detroit", "leeds", "london", "los angeles", "louisville",
            "melbourne", "moscow", "munich", "new york city",
            "omaha", "paris", "philadelphia", "pittsburgh",
            "san diego", "seattle", "stamford", "tokyo",
            "toronto", "tirana", "porto", "milwaukee",
            "chennai",
            # Regions
            "appalachia", "capital district", "east anglia",
            "greater manchester", "hudson valley",
            "jammu and kashmir", "tamil nadu",
            "wiltshire", "yugoslavia",
            # Countries / regions as geography
            "abkhazia", "andhra pradesh", "assam", "bengal",
            "buckinghamshire", "cheshire", "cornwall", "derbyshire",
            "devon", "gujarat", "haryana", "hertfordshire",
            "lancashire", "lincolnshire", "madhya pradesh",
            "new south wales", "northern territory", "punjab",
            "queensland", "rajasthan", "somerset", "surrey", "sussex",
            "tasmania", "victoria", "yorkshire",
            "kurdistan", "ossetia", "tibet",
            "caribbean", "polynesia",
            # Generic geographic terms
            "africa", "americas", "asia", "europe", "oceania",
            "antarctica", "country", "island", "river", "lake",
            "mountain", "volcano", "region", "province",
        ], [
            # Exclude history/science terms that collide with place names
            "ancient", "medieval", "roman", "byzantine",
            "empire", "monarchy", "royalty", "dynasty",
            "crusade", "prehistory", "historic", "heritage",
            "world war", "cold war", "soviet", "napoleonic",
            "tropical cyclone", "hurricane", "earthquake",
            "volcano", "environment",
        ]),

        # ── 2. Transportation ─────────────────────────────────────────
        # Elevated to top-level for discoverability. 81 projects covering
        # aviation, roads, rail, shipping, transit. Vital hierarchy buries
        # this under "Everyday life" which is too vague for an editor
        # searching for transport content.
        ("Transportation", [
            "transport", "road", "roads", "highway", "highways",
            "railway", "train", "trains", "bus", "buses",
            "aviation", "aircraft", "airport", "airports",
            "airline", "airlines",
            "ship", "ships", "shipwreck", "shipwrecks",
            "street", "car", "cars", "motor", "cycling", "traffic",
            "bridge", "bridges", "tunnel", "tunnels",
            "rail", "tram", "metro", "subway", "navigation",
            "flight", "spaceflight", "automobile", "automobiles",
            "truck", "trucks",
            "bicycle", "scooter", "transit", "streetcars", "shipping",
            "gliding", "rail transport", "uk railways",
            "locomotive", "railroad", "highways", "motorcycles",
            "motorcycling", "ferry", "ferries",
        ], []),

        # ── 3. Sports & Games ─────────────────────────────────────────
        # Elevated to top-level for discoverability. 61 projects covering
        # all major sports, board games, video games, esports. Vital
        # hierarchy buries this under "Everyday life."
        ("Sports & Games", [
            "sport", "athletic", "football", "soccer", "baseball",
            "basketball", "tennis", "golf", "cricket", "rugby",
            "hockey", "ice hockey", "skiing", "swimming", "boxing",
            "wrestling", "martial arts", "karate", "judo", "taekwondo",
            "fencing", "archery", "shooting", "cycling", "motorcycle",
            "motorsport", "nascar", "formula", "auto racing",
            "olympic", "paralympic", "volleyball", "handball",
            "skateboarding", "snowboard", "surfing", "climbing",
            "canoe", "rowing", "sailing", "equestrian",
            "weightlifting", "gymnastics", "cheerleading",
            "lacrosse", "polo", "water polo", "badminton",
            "table tennis", "squash", "bowling", "billiard",
            "darts", "hunting", "paintball", "parkour",
            "mixed martial arts", "mma", "kickboxing",
            "netball", "floorball", "chess", "board game",
            "role-playing game", "video game", "esports",
            "curling", "bobsleigh", "speed skating",
            "figure skating", "biathlon",
            "horse racing", "snooker", "poker", "running",
            "dungeons & dragons", "magic: the gathering",
            "halo", "transformers", "g.i. joe", "green bay packers",
            "big 12 conference", "american football",
            "american football league", "american open wheel racing",
            "australian rules football", "lanka premier league",
            "weekly sports", "cue sports", "big brother",
            "lacrosse",
            # Plural / missing forms
            "sports", "games", "athletics",
            "video games", "video games/nintendo", "video games/sega",
            "role-playing games",
            "olympics", "paralympics", "olympic",
            "go", "board games",
            "gambling",
        ], []),

        # ── 4. Wikipedia Maintenance ──────────────────────────────────
        # NEW category. ~30 projects about Wikipedia itself (not about
        # encyclopedic content). No Vital Articles equivalent — these are
        # meta-projects unique to the WikiProject system.
        ("Wikipedia Maintenance", [
            "abandoned articles", "articles for creation",
            "disambiguation", "lists", "wikify",
            "introductions", "stub improvement",
            "missing encyclopedic articles",
            "countering systemic bias",
            "article rescue squadron",
            "reference desk article collaboration",
            "adoption, fostering, orphan care and displacement",
            "alternative views", "wikiproject wikipedia",
            "ai cleanup", "unrecognized countries",
            "category", "cities", "countries",
            "glossaries", "indexes", "outlines",
            "years", "timeline tracer",
            "meta",
            "wikipedia",
        ], []),

        # ── 5. Health, Medicine & Biology ─────────────────────────────
        # Expanded from Vital's "Biological and health sciences" to
        # absorb ~50 animal/plant/fungi subfields (Birds, Fish, Mammals,
        # Dinosaurs, Fungi, Plants, etc.) that would otherwise be
        # uncategorized.
        ("Health, Medicine & Biology", [
            "medicine", "medical", "health", "disease", "biology",
            "genetics", "neuroscience", "immunology", "virology",
            "bacteriology", "microbiology", "anatomy", "physiology",
            "botany", "zoology", "ecology", "mycology", "entomology",
            "ornithology",
            "mammal", "mammals", "reptile", "reptiles",
            "amphibian", "amphibians", "arthropod", "arthropods",
            "arachnid", "arachnids", "insect", "insects",
            "fish", "fishes", "bird", "birds", "algae", "fungus", "fungi",
            "evolution", "palaeontology", "paleont", "fossil",
            "veterinary", "dentistry", "nursing", "pharmacy", "optometry",
            "public health", "sexology", "psychology", "psychiatry",
            "toxicology", "cancer", "aids", "epilepsy", "autism",
            "addiction", "addictions", "alternative medicine", "homeopathy",
            "chiropractic", "parapsychology", "disability",
            "mental health", "diet", "ageing",
            "dinosaur", "dinosaurs", "mammoth", "pterosaur",
            "animal", "animals", "canine", "feline",
            "dog", "dogs", "cat", "cats", "horse", "horses",
            "equine", "rodent", "rodents", "bat", "primate", "primates",
            "shark", "sharks", "turtle", "turtles",
            "snake", "lizard", "frog", "toad", "salamander",
            "crab", "lobster", "shrimp", "spider", "spiders", "scorpion",
            "centipede", "millipede", "worm", "leech",
            "snail", "slug", "clam", "oyster", "mussel",
            "coral", "jellyfish", "anemone", "sponge",
            "starfish", "sea urchin",
            "cephalopod", "gastropod", "bivalve",
            "bivalves", "cephalopods", "gastropods",
            "lepidoptera", "mantodea", "phasmatodea", "hymenoptera",
            "diptera", "coleoptera", "hemiptera",
            "arachnida", "crustacean", "plankton",
            "cetacean", "cetaceans", "pinniped", "sirenian",
            "marsupial", "marsupials", "monotreme", "monotremes",
            "carnivorous plant", "carnivorous plants",
            "tree of life", "hypericaceae", "banksia",
            "pteridophyte", "pteridophytes",
            "protista", "lichen", "cactus", "cacti",
            "aquarium", "beetle", "beetles", "caterpillar",
            "cryptozoology", "extinction",
            "covid-19", "sanitation", "hospital", "hospitals",
            "pharmacology", "first aid", "emergency",
            "dietary supplements", "herbalism",
            "cannabis", "virus", "viruses",
            "biota", "aquatic invertebrates",
            "dietary supplements",
            "plants",
        ], []),

        # ── 6. Physical Sciences ──────────────────────────────────────
        # Physics, Astronomy, Chemistry, Earth Sciences kept together
        # as Vital does, since editors expect to find them grouped.
        ("Physical Sciences", [
            "physics", "astronomy", "astrophysics", "cosmology",
            "spaceflight", "astronomical", "constellation", "jupiter",
            "mars", "nebula", "galaxy", "star", "planet",
            "solar system", "astrology",
            "chemistry", "chemical", "element", "isotope",
            "geology", "geography", "earthquake",
            "volcano", "desert", "ocean", "marine", "weather",
            "climate", "hurricane", "tropical cyclone", "tsunami",
            "meteorite", "mineral", "soil", "limnology",
            "oceanography", "earth", "seamount",
            "mountains of the alps", "wildfire",
            "ecoregion", "ecoregions", "protected area", "protected areas",
            "mass spectrometry", "measurement",
            # Missing physical science terms
            "environment",
            "chemicals",
            "tropical cyclones",
            "volcanoes", "mountains", "lakes", "rivers", "islands",
            "earthquakes", "elements",
        ], ["biota", "aquatic"]),

        # ── 7. Mathematics ────────────────────────────────────────────
        ("Mathematics", [
            "mathematics", "math", "statistics", "probability",
            "geometry", "algebra", "number theory", "calculus",
            "mathematical", "polytope", "uniform polytope",
            "mathematics competitions",
        ], []),

        # ── 8. Technology & Engineering ───────────────────────────────
        ("Technology & Engineering", [
            "engineering", "technology", "computer", "software",
            "computing", "programming", "algorithm", "database",
            "robotics", "telecommunications", "electronics",
            "signal processing", "artificial intelligence",
            "machine learning", "internet", "website", "cyber",
            "information technology", "amiga", "java", "javascript",
            "python", "linux", "apple inc", "android",
            "aircraft", "aircraft/engines",
            "microsoft", "google", "intel", "amd", "ibm",
            "microsoft windows", "risc os",
            "cryptography", "cryptocurrency",
            "energy", "nuclear technology",
            "professional sound production",
            "industrial design",
            "invention", "measurement",
            "webcomics", "websites",
            "databases", "systems", "open", "open source", "open content",
        ], []),

        # ── 9. Business & Economics ───────────────────────────────────
        # Elevated to top-level per user direction. Vital hierarchy
        # buries this under "Society and social sciences," but Business
        # is one of the largest WikiProject clusters by editor interest
        # and article volume. Pragmatism over hierarchy.
        ("Business & Economics", [
            "economics", "finance", "business", "banking", "trade",
            "market", "investment", "insurance", "accounting",
            "company", "industry", "manufacturing", "employment",
            "marketing", "entrepreneurship", "management",
            "consulting", "advertising", "commerce", "retail",
            "wholesale", "logistics", "supply chain", "startup",
            "corporation", "enterprise", "venture capital",
            "finance & investment", "marketing & advertising",
            "taxation", "shopping centers", "retailing",
            "brands", "cooperatives",
            "home living", "real estate",
            "organized labour",
            "companies",
        ], []),

        # ── 10. Society & Social Sciences ─────────────────────────────
        # Politics, Law, Education, Media, Journalism grouped as Vital
        # does. Education and Media are large enough to be distinct
        # subcategories within this group.
        ("Society & Social Sciences", [
            "politics", "government", "law", "constitution",
            "election", "political party", "legislation", "justice",
            "human rights", "anarchism", "libertarian", "socialist",
            "communism", "fascism", "democracy", "diplomacy",
            "treaty", "lobbying", "propaganda", "censorship",
            "voting", "parliament", "senate", "congress",
            "supreme court", "corruption", "policy", "regulation",
            "executive", "judicial", "legislative", "federal",
            "presidents of the united states",
            "conservatism", "socialism",
            "international relations", "nato",
            "education", "university", "college", "school",
            "academy", "student", "professor", "teacher",
            "teaching", "learning", "curriculum", "assessment",
            "scholarship", "research", "academic", "campus",
            "faculty", "department", "lecture", "classroom",
            "laboratory", "observatory", "planetarium",
            "academic journals", "higher education",
            "journalism", "media", "newspaper", "magazine",
            "press", "news", "radio", "podcast", "broadcast",
            "publication", "editor", "reporter",
            "social media", "television news", "news agency",
            "amateur radio", "ham radio",
            "sociology", "anthropology", "archaeology",
            "gender studies", "lgbtq+ studies",
            "black lives matter", "civil rights movement",
            "feminism", "discrimination", "freedom of speech",
            "skepticism", "urban studies",
            "international development",
            "occupations", "organizations",
            # Missing social topics
            "accessibility", "african diaspora", "asian americans",
            "correction and detention facilities",
            "firearms", "globalization",
            "indigenous peoples", "social work",
            "united nations", "elections and referendums",
            "latin america", "central america",
            "squatting", "freemasonry",
            "schools", "science",
            "georgia tech", "notre dame", "mizzou", "suny",
            "science",
        ], []),

        # ── 11. History ───────────────────────────────────────────────
        # Absorbs Military sub-projects which are effectively history
        # subfields.
        ("History", [
            "history", "ancient", "medieval", "renaissance",
            "world war", "military history", "military",
            "crusade", "roman", "byzantine", "empire",
            "monarchy", "royalty", "civilization", "dynasty",
            "colonial", "genealogy", "numismatics", "philately",
            "heraldry", "castle", "holocaust", "napoleonic",
            "cold war", "soviet", "historic", "heritage",
            "middle ages", "prehistory",
            "army", "navy", "air force", "marine",
            "weapon", "missile", "battle", "warfare",
            "defense", "fortification", "medal", "award",
            "veteran", "soldier", "sailor",
            "artillery", "infantry", "cavalry", "armor",
            "tank", "submarine", "warship",
            "aircraft carrier", "battleship", "destroyer",
            "frigate", "cruiser",
            "anglo-saxon kingdoms", "viking",
            "piracy", "phoenicia",
            "clans of scotland", "peerage and baronetage",
        ], []),

        # ── 12. Arts & Culture ────────────────────────────────────────
        # Unified top-level that absorbs Music, Film/TV, Literature,
        # Visual Arts, and Performing Arts into one navigable group.
        # These were separate domains in our initial classification but
        # Vital groups them — and the 57 total projects don't warrant
        # 5 separate picker sections. The picker can offer sub-filters
        # within the category.
        ("Arts & Culture", [
            "music", "song", "album", "singer", "guitar",
            "piano", "orchestra", "opera", "jazz", "blues",
            "folk", "rock", "pop music", "hip hop", "electronic",
            "classical music", "heavy metal", "punk",
            "country music", "reggae", "soul", "r&b", "funk",
            "disco", "techno", "house music", "drum", "bass",
            "gospel", "rap", "grammy", "billboard", "musician",
            "composer", "concert", "festival", "instrument",
            "band", "choir", "quartet",
            "record labels", "record production",
            "discographies", "record chart",
            "professional sound production",
            "film", "movie", "cinema", "animation", "television",
            "tv", "series", "netflix", "bbc", "show", "sitcom",
            "game show", "broadcasting", "documentary",
            "studio", "cartoon", "pixar", "disney",
            "marvel cinematic", "actor", "filmmaker",
            "hollywood", "bollywood",
            "nickelodeon", "cartoon network",
            "literature", "book", "novel", "poetry", "play",
            "writer", "author", "fantasy", "science fiction",
            "mystery", "comics", "manga", "anime",
            "webcomic", "bibliography", "library",
            "magazine", "publishing",
            "a song of ice and fire", "harry potter",
            "star wars", "star trek", "doctor who",
            "the beatles", "shakespeare",
            "art", "painting", "sculpture", "photography",
            "drawing", "illustration", "fashion", "color",
            "tattoo", "museum", "gallery", "exhibition",
            "craft", "pottery", "ceramic", "glass",
            "woodworking", "metalworking", "jewelry",
            "gemology", "lapidary", "graffiti",
            "printmaking", "calligraphy", "typography",
            "graphic", "decorative", "textile",
            "theatre", "theater", "dance", "ballet", "circus",
            "musical theatre", "comedy", "broadway",
            "visual arts", "popular culture",
            "fictional characters", "horror",
            "composers", "actors and filmmakers",
            # Plural forms and missed media
            "songs", "albums", "books", "novels",
            "magazines", "newspapers",
            "architecture", "museums",
            "writing", "writers",
            "south park", "the simpsons", "eastenders",
            "20th century studios",
            "westerns", "post-hardcore",
            "metal", "rapper",
            "films", "square enix",
            "alien",
        ], []),

        # ── 13. Philosophy & Religion ─────────────────────────────────
        # Kept together as Vital does — two small domains that share
        # conceptual overlap and user expectations.
        ("Philosophy & Religion", [
            "philosophy", "logic", "ethics", "metaphysics",
            "epistemology", "aesthetics", "philosophy of",
            "objectivism",
            "religion", "christianity", "islam", "hinduism",
            "buddhism", "judaism", "sikhism", "mythology",
            "bible", "church", "theology", "saint", "atheism",
            "spirituality", "kabbalah", "mormon", "quaker",
            "jehovah", "falun gong", "scientology",
            "wicca", "pagan", "zoroastrian", "shinto", "taoism",
            "confucianism", "bahai", "rastafari", "babism",
            "anglican", "catholic", "protestant", "orthodox",
            "methodist", "baptist", "lutheran", "presbyterian",
            "pentecostal", "evangelical",
            "hebrew", "rabbi", "torah", "talmud",
            "thelema", "occult", "paranormal",
            "folklore", "saints",
            "eastern orthodoxy", "anglicanism",
            "lutheranism", "catholicism",
            "creationism", "jainism",
            # Languages (no dedicated category; closest fit)
            "languages", "linguistics", "constructed languages",
            "latin", "anthroponymy",
            # Borderline philosophy topics
            "altered states of consciousness",
        ], []),

        # ── 14. People & Biography ────────────────────────────────────
        # Vital's "People" category. Handles individual artists,
        # celebrities, bands that are organized as individual
        # WikiProjects (Beyoncé, The Beatles, Taylor Swift, etc.).
        ("People & Biography", [
            "people", "biography", "women in", "women of",
            "women", "afrocreatives",
            "beyonce", "taylor swift", "adele", "ed sheeran",
            "britney spears", "billie eilish", "miley cyrus",
            "kelly clarkson", "meghan trainor", "olivia rodrigo",
            "kylie minogue", "madonna", "mariah carey",
            "rihanna", "shakira", "katy perry", "lady gaga",
            "bob dylan", "beyonce", "bjork",
            "elvis presley", "frank sinatra", "michael jackson",
            "prince", "david bowie", "freddie mercury",
            "queen", "madonna",
            "the beatles", "rolling stones", "led zeppelin",
            "pink floyd", "nirvana", "u2", "coldplay",
            "radiohead", "the clash", "the kinks",
            "aerosmith", "guns n' roses", "metallica",
            "eminem", "jay-z", "kanye west",
            "britney spears", "christina aguilera",
            "justin timberlake", "beyonce",
            "taylor swift", "ariana grande",
            "selena gomez", "demi lovato",
            "men's issues", "queensland",
            "musicians", "artists",
            # Individual artists / bands
            "beyoncé", "alexandra stan", "björk", "inna",
            "rufus wainwright",
        ], []),

        # ── 15. Everyday Life & Food ──────────────────────────────────
        # Remnants from Vital's "Everyday life" after Sports and
        # Transportation were elevated. Agriculture, food, drink,
        # amusements, and general lifestyle projects.
        ("Everyday Life & Food", [
            "agriculture", "food", "drink", "beer", "wine",
            "fishing", "forest", "farm", "crop", "garden",
            "nutrition", "cooking", "recipe", "bacon",
            "herb", "spice", "beverage", "pub",
            "poultry", "livestock",
            "dessert", "breakfast", "bread",
            "fisheries and fishing",
            "horticulture and gardening", "forestry",
            "amusement parks", "toys",
            "travel and tourism", "camping", "backpacking",
            "home living", "pets",
            "nudity", "pornography", "sexuality",
            "romance", "dating",
            "death", "funeral", "time",
            "scouting", "yoga",
            "homeopathy",
            "spirits",
            "underwater diving",
        ], []),
    ]

    for domain, keywords, excludes in rules:
        for kw in keywords:
            if re.search(wb(kw), lower):
                excluded = False
                for ex in excludes:
                    if re.search(wb(ex), lower):
                        excluded = True
                        break
                if not excluded:
                    return domain

    return 'Other / Uncategorized'


def main():
    names = fetch_project_names()
    print(f"Loaded {len(names)} WikiProject names\n")

    groups = {}
    for n in names:
        domain = classify_domain(n)
        groups.setdefault(domain, []).append(n)

    print(f"{'Domain':40s} {'Count':>5s}")
    print("-" * 48)
    max_cnt = max(len(g) for g in groups.values())
    for domain in sorted(groups.keys(), key=lambda d: -len(groups[d])):
        cnt = len(groups[domain])
        bar = '█' * (cnt * 40 // max_cnt) if max_cnt else ''
        print(f"{domain:40s} {cnt:5d}  {bar}")
    print("-" * 48)
    print(f"{'TOTAL':40s} {len(names):5d}")

    if 'Other / Uncategorized' in groups:
        other = groups['Other / Uncategorized']
        print(f"\n--- Uncategorized ({len(other)}) ---")
        for n in other:
            print(f"  {n}")

    print(f"\n--- Sample entries per domain ---")
    for domain in sorted(groups.keys(), key=lambda d: -len(groups[d])):
        samples = groups[domain][:4]
        print(f"\n  {domain} ({len(groups[domain])}):")
        for s in samples:
            print(f"    {s}")

    manifest = {
        "version": 1,
        "generated": "2026-05-14T00:00:00Z",
        "total_projects": len(names),
        "domains": {}
    }
    for domain in sorted(groups.keys(), key=lambda d: -len(groups[d])):
        manifest["domains"][domain] = []
        for n in groups[domain]:
            slug = "wp_" + re.sub(r'[^a-z0-9]', '_', n.lower()).strip('_')
            slug = re.sub(r'_+', '_', slug)
            manifest["domains"][domain].append({
                "name": n,
                "slug": slug,
                "articles": 0,
                "date_gen": None,
                "limit": 500
            })

    print(f"\n\n--- Manifest JSON (first 4000 chars) ---")
    print(json.dumps(manifest, indent=2)[:4000])


if __name__ == '__main__':
    main()
