from __future__ import annotations

from django.db import models

# How many builder prompts a published run may offer.
MAX_BUILDER_PROMPTS = 4


class SDG(models.IntegerChoices):
    """The 17 UN Sustainable Development Goals. Fixed global constants, so they live in code
    rather than a table - no seed migration and no way to mistype one."""

    no_poverty = 1, "No Poverty"
    zero_hunger = 2, "Zero Hunger"
    good_health_and_well_being = 3, "Good Health and Well-being"
    quality_education = 4, "Quality Education"
    gender_equality = 5, "Gender Equality"
    clean_water_and_sanitation = 6, "Clean Water and Sanitation"
    affordable_and_clean_energy = 7, "Affordable and Clean Energy"
    decent_work_and_economic_growth = 8, "Decent Work and Economic Growth"
    industry_innovation_and_infrastructure = (
        9,
        "Industry, Innovation and Infrastructure",
    )
    reduced_inequalities = 10, "Reduced Inequalities"
    sustainable_cities_and_communities = 11, "Sustainable Cities and Communities"
    responsible_consumption_and_production = (
        12,
        "Responsible Consumption and Production",
    )
    climate_action = 13, "Climate Action"
    life_below_water = 14, "Life Below Water"
    life_on_land = 15, "Life on Land"
    peace_justice_and_strong_institutions = 16, "Peace, Justice and Strong Institutions"
    partnerships_for_the_goals = 17, "Partnerships for the Goals"

    @property
    def un_url(self) -> str:
        return f"https://sdgs.un.org/goals/goal{self.value}"

    @property
    def icon_url(self) -> str:
        return (
            "https://sdgs.un.org/sites/default/files/goals/"
            f"E_SDG_Icons-{self.value:02d}.jpg"
        )
