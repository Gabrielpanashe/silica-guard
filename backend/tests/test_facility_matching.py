from services.facility_matching import select_facility

HOSPITAL = {"id": 1, "name": "Kwekwe District Hospital", "level": "district_hospital"}
SECOND_HOSPITAL = {"id": 5, "name": "Second Hospital", "level": "district_hospital"}
SHERWOOD_CLINIC = {"id": 2, "name": "Sherwood Clinic", "level": "clinic"}
OTHER_CLINIC = {"id": 3, "name": "Globe Clinic", "level": "clinic"}

ALL_FACILITIES = [HOSPITAL, SHERWOOD_CLINIC, OTHER_CLINIC]


def test_red_always_matches_hospital_regardless_of_site():
    result = select_facility("RED", "Sherwood Mine", ALL_FACILITIES)
    assert result["id"] == HOSPITAL["id"]


def test_red_matches_hospital_even_with_no_site():
    result = select_facility("RED", None, ALL_FACILITIES)
    assert result["id"] == HOSPITAL["id"]


def test_orange_matches_clinic_by_site_name():
    result = select_facility("ORANGE", "Sherwood Mine", ALL_FACILITIES)
    assert result["id"] == SHERWOOD_CLINIC["id"]


def test_orange_falls_back_to_hospital_when_no_clinic_matches():
    result = select_facility("ORANGE", "Kwekwe Consolidated", ALL_FACILITIES)
    assert result["id"] == HOSPITAL["id"]


def test_orange_falls_back_to_hospital_with_no_site():
    result = select_facility("ORANGE", None, ALL_FACILITIES)
    assert result["id"] == HOSPITAL["id"]


def test_multiple_hospitals_lowest_id_wins():
    facilities = [SECOND_HOSPITAL, HOSPITAL]  # deliberately out of id order
    result = select_facility("RED", None, facilities)
    assert result["id"] == HOSPITAL["id"]


def test_empty_facilities_returns_none():
    assert select_facility("RED", "Sherwood Mine", []) is None
    assert select_facility("ORANGE", "Sherwood Mine", []) is None


def test_unrecognised_tier_falls_back_to_hospital():
    result = select_facility("YELLOW", "Sherwood Mine", ALL_FACILITIES)
    assert result["id"] == HOSPITAL["id"]
