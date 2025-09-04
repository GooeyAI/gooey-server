from bots.models import Tag, TagCategory

DEFAULT_TAGS = [
    Tag(name="Agriculture", icon="🌱", category=TagCategory.industry),
    Tag(name="Education", icon="🎓", category=TagCategory.industry),
    Tag(name="Marketing", icon="📈", category=TagCategory.industry),
    Tag(name="Government", icon="🏛️", category=TagCategory.industry),
    Tag(name="Trades", icon="🛠️", category=TagCategory.industry),
    Tag(name="Culture", icon="🎭", category=TagCategory.industry),
    Tag(name="Health", icon="🩺", category=TagCategory.industry),
    Tag(name="Telco", icon="📡", category=TagCategory.industry),
    Tag(name="Kenya", icon="🇰🇪", category=TagCategory.region),
    Tag(name="India", icon="🇮🇳", category=TagCategory.region),
    Tag(name="Africa", icon="🌍", category=TagCategory.region),
    Tag(name="US", icon="🇺🇸", category=TagCategory.region),
]


def run():
    Tag.objects.bulk_create(DEFAULT_TAGS, ignore_conflicts=True)
