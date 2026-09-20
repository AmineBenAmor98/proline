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


class Frequency(str, enum.Enum):
    one_time = "one_time"
    weekly = "weekly"
    biweekly = "biweekly"
    monthly = "monthly"
    to_discuss = "to_discuss"


class RequestStatus(str, enum.Enum):
    new = "new"
    enriching = "enriching"
    priced = "priced"
    quoted = "quoted"
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
    workstations = "workstations"
    restrooms = "restrooms"
    hallways = "hallways"
    common_areas = "common_areas"
    kitchen = "kitchen"
    other = "other"
