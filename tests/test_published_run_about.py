from bots.sdg import SDG


def test_sdg_covers_all_seventeen_goals():
    assert [g.value for g in SDG] == list(range(1, 18))
    assert SDG(1).label == "No Poverty"
    assert SDG(17).label == "Partnerships for the Goals"


def test_sdg_urls_are_derived_from_the_number():
    """Zero-padded in the icon filename, bare in the goal url - the UN uses both."""
    assert SDG(1).icon_url.endswith("E_SDG_Icons-01.jpg")
    assert SDG(17).icon_url.endswith("E_SDG_Icons-17.jpg")
    assert SDG(1).un_url == "https://sdgs.un.org/goals/goal1"
    assert SDG(17).un_url == "https://sdgs.un.org/goals/goal17"
