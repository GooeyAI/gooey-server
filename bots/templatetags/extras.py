import json

from django import template

register = template.Library()


@register.filter
def pretty_json(value):
    if isinstance(value, str):
        value = json.loads(value)
    return json.dumps(value, indent=2)
