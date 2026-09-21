"""Starting values a new rate card can be built from.

These live here rather than in `scripts/seed_rate_card.py` because two things
need them: the seed script, and `/admin/tarifs`, which offers them to a card that
predates a feature. A card seeded before modifiers existed has none, and building
four questions by hand -- each with two or three answers, in two languages -- is
enough friction that the feature would simply go unused.

EVERY NUMBER HERE IS A PLACEHOLDER, like everything else about pricing in this
repo. The multipliers in particular are the values most likely to be wrong,
because only real jobs can settle them: log quoted vs actual hours and correct
them in /admin/tarifs.
"""

STANDARD_MODIFIERS: dict[str, dict] = {
    "premier_menage": {
        "sort": 10,
        "label_fr": "Est-ce un premier ménage ?",
        "label_en": "Is this a first clean?",
        "short_fr": "Premier ménage",
        "short_en": "First clean",
        "help_fr": "Un premier passage prend plus de temps qu'un entretien régulier.",
        "help_en": "A first visit takes longer than regular upkeep.",
        "options": [
            {"value": "no", "label_fr": "Non, entretien régulier",
             "label_en": "No, regular upkeep"},
            {"value": "yes", "label_fr": "Oui", "label_en": "Yes", "multiplier": "1.4"},
        ],
    },
    "etat": {
        "sort": 20,
        "label_fr": "État du logement",
        "label_en": "Condition of the home",
        "short_fr": "État",
        "short_en": "Condition",
        "options": [
            {"value": "normal", "label_fr": "Normal", "label_en": "Normal"},
            {"value": "encombre", "label_fr": "Encombré", "label_en": "Cluttered",
             "multiplier": "1.2"},
            {"value": "tres_sale", "label_fr": "Très sale", "label_en": "Very dirty",
             "multiplier": "1.45"},
        ],
    },
    "animaux": {
        "sort": 30,
        "label_fr": "Animaux à la maison",
        "label_en": "Pets at home",
        "short_fr": "Animaux",
        "short_en": "Pets",
        "options": [
            {"value": "none", "label_fr": "Aucun", "label_en": "None"},
            {"value": "one", "label_fr": "Un", "label_en": "One", "cents": 1000},
            {"value": "many", "label_fr": "Deux ou plus", "label_en": "Two or more",
             "cents": 2000},
        ],
    },
    "vide": {
        "sort": 40,
        "label_fr": "Le logement est-il vide ?",
        "label_en": "Is the home empty?",
        "short_fr": "Logement vide",
        "short_en": "Empty home",
        "help_fr": "Sans meubles : fin de bail, déménagement, avant emménagement.",
        "help_en": "No furniture: end of lease, moving out, before moving in.",
        "options": [
            {"value": "no", "label_fr": "Non, meublé et occupé",
             "label_en": "No, furnished and lived in"},
            {"value": "yes", "label_fr": "Oui", "label_en": "Yes", "multiplier": "1.15"},
        ],
    },
}
