import enum


class Audience(str, enum.Enum):
    residential = "residential"
    commercial = "commercial"


class PropertyType(str, enum.Enum):
    house = "house"
    condo = "condo"
    apartment = "apartment"
    office = "office"
    retail = "retail"
    building = "building"
    industrial = "industrial"
    construction = "construction"


# A property type belongs to exactly one audience. This is the single source of
# truth for that pairing: the API rejects any request that contradicts it, and the
# quote form derives the audience from the property type rather than asking twice.
AUDIENCE_BY_PROPERTY_TYPE: dict["PropertyType", "Audience"] = {
    PropertyType.house: Audience.residential,
    PropertyType.condo: Audience.residential,
    PropertyType.apartment: Audience.residential,
    PropertyType.office: Audience.commercial,
    PropertyType.retail: Audience.commercial,
    PropertyType.building: Audience.commercial,
    PropertyType.industrial: Audience.commercial,
    PropertyType.construction: Audience.commercial,
}


class Frequency(str, enum.Enum):
    one_time = "one_time"
    weekly = "weekly"
    biweekly = "biweekly"
    monthly = "monthly"
    to_discuss = "to_discuss"


class RequestStatus(str, enum.Enum):
    """Where a request stands with the client. Nothing else.

    It used to also carry `priced` and `enriching`. `priced` was set on arrival
    whenever the engine produced a number, which made it a restatement of
    `computed_total_cents IS NULL` -- and meant a request nobody had opened
    arrived already "Chiffrée", so the inbox had no unread state. `enriching` was
    never set by anything.
    """

    new = "new"          # arrived, nobody has dealt with it
    quoted = "quoted"    # a price was sent to the client
    won = "won"
    lost = "lost"


class ServiceCode(str, enum.Enum):
    residential_cleaning = "residential_cleaning"
    office_cleaning = "office_cleaning"
    common_areas = "common_areas"
    post_construction = "post_construction"
    end_of_lease = "end_of_lease"
    floor_stripping_waxing = "floor_stripping_waxing"
    carpets = "carpets"
    windows = "windows"
    garage = "garage"
    waste_management = "waste_management"


class PhotoZone(str, enum.Enum):
    """Where in the property a photo was taken.

    ONE enum for both audiences, not two. A zone is a fact about the photo, and
    splitting it by audience would mean a second enum, a second column or a
    discriminator -- for a distinction the form already knows and can simply
    filter on. ZONES_BY_AUDIENCE below is what each form offers; the database
    accepts any of them, because a commercial building has a kitchen and a
    triplex has a corridor, and refusing that at the column is a rule nobody
    asked for.
    """

    # Commercial-leaning
    workstations = "workstations"
    restrooms = "restrooms"
    hallways = "hallways"
    common_areas = "common_areas"
    # Residential-leaning
    bathroom = "bathroom"
    bedroom = "bedroom"
    living_area = "living_area"
    basement = "basement"
    garage = "garage"
    # Either
    kitchen = "kitchen"
    entrance = "entrance"
    exterior = "exterior"
    other = "other"


# What each form offers, in the order it offers it. `other` is last on purpose:
# it is the escape hatch, not a suggestion.
ZONES_BY_AUDIENCE: dict[str, tuple[PhotoZone, ...]] = {
    "residential": (
        PhotoZone.kitchen,
        PhotoZone.bathroom,
        PhotoZone.bedroom,
        PhotoZone.living_area,
        PhotoZone.entrance,
        PhotoZone.basement,
        PhotoZone.garage,
        PhotoZone.exterior,
        PhotoZone.other,
    ),
    "commercial": (
        PhotoZone.workstations,
        PhotoZone.restrooms,
        PhotoZone.hallways,
        PhotoZone.common_areas,
        PhotoZone.kitchen,
        PhotoZone.entrance,
        PhotoZone.exterior,
        PhotoZone.other,
    ),
}

PHOTO_ZONE_LABELS_FR: dict[PhotoZone, str] = {
    PhotoZone.workstations: "Postes de travail",
    PhotoZone.restrooms: "Toilettes",
    PhotoZone.hallways: "Corridors",
    PhotoZone.common_areas: "Aires communes",
    PhotoZone.bathroom: "Salle de bain",
    PhotoZone.bedroom: "Chambre",
    PhotoZone.living_area: "Aire de vie",
    PhotoZone.basement: "Sous-sol",
    PhotoZone.garage: "Garage",
    PhotoZone.kitchen: "Cuisine",
    PhotoZone.entrance: "Entrée",
    PhotoZone.exterior: "Extérieur",
    PhotoZone.other: "Autre",
}

PHOTO_ZONE_LABELS_EN: dict[PhotoZone, str] = {
    PhotoZone.workstations: "Workstations",
    PhotoZone.restrooms: "Restrooms",
    PhotoZone.hallways: "Hallways",
    PhotoZone.common_areas: "Common areas",
    PhotoZone.bathroom: "Bathroom",
    PhotoZone.bedroom: "Bedroom",
    PhotoZone.living_area: "Living area",
    PhotoZone.basement: "Basement",
    PhotoZone.garage: "Garage",
    PhotoZone.kitchen: "Kitchen",
    PhotoZone.entrance: "Entrance",
    PhotoZone.exterior: "Exterior",
    PhotoZone.other: "Other",
}
