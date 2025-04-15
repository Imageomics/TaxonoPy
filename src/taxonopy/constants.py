from collections import OrderedDict

# The seven standard Linnaean ranks
TAXONOMIC_RANKS = ['kingdom', 'phylum', 'class_', 'order', 'family', 'genus', 'species']

TAXONOMIC_RANKS_BY_SPECIFICITY = list(reversed(TAXONOMIC_RANKS))

# Define taxonomic ranks in order of precedence for query term selection
TAXONOMIC_QUERY_PRECEDENCE = [
    ("species", "species"),
    ("scientific_name", "scientific_name"),
    ("genus", "genus"),
    ("family", "family"),
    ("order", "order"),
    ("class_", "class"),
    ("phylum", "phylum"),
    ("kingdom", "kingdom")
]

# Define data sources in order of preference
DATA_SOURCE_PRECEDENCE = OrderedDict([
    ("GBIF", 11),
    ("COL", 1),
    ("OTOL", 179),
#     ("NCBI", 4),
#     ("Wikidata", 207),
#     ("IndexFungorum", 5),
#     ("MycoBank", 203),
#     ("WoRMS", 9),
#     ("ICTV", 201)
])

INVALID_VALUES = ['unknown', 'null', 'none', '', 'n/a']
