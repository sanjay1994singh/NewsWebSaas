class TrimmedFormMixin:
    """Trim leading/trailing whitespace from string form values before save/use."""

    def clean(self):
        cleaned_data = super().clean()
        for name, value in list(cleaned_data.items()):
            if isinstance(value, str):
                cleaned_data[name] = value.strip()
        return cleaned_data