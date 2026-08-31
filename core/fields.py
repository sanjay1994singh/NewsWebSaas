import json

from django.core.exceptions import ValidationError
from django.db import models


class JSONTextField(models.TextField):
    description = "JSON object stored as portable text"

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('default', dict)
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        if kwargs.get('default') is dict:
            kwargs.pop('default')
        return name, path, args, kwargs

    def from_db_value(self, value, expression, connection):
        return self.to_python(value)

    def to_python(self, value):
        if value is None or isinstance(value, (dict, list)):
            return value
        if value == '':
            return {}
        try:
            return json.loads(value)
        except (TypeError, ValueError) as exc:
            raise ValidationError("Invalid JSON value.") from exc

    def get_prep_value(self, value):
        if value is None:
            return None
        return json.dumps(value)
