from django.test import SimpleTestCase
from subscriptions.forms import OnboardingForm
from themes.templatetags.theme_colors import readable_color


class ThemeColorTests(SimpleTestCase):
    def test_form_normalizes_and_rejects_invalid_css(self):
        form = OnboardingForm()
        form.cleaned_data = {'primary_color': '#ABCDEF'}
        self.assertEqual(form.clean_primary_color(), '#abcdef')
        form.cleaned_data['primary_color'] = 'red; background:url(x)'
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            form.clean_primary_color()

    def test_legacy_invalid_values_use_safe_default(self):
        self.assertEqual(readable_color('</style>'), '#0b6b57')
        self.assertEqual(readable_color(None), '#0b6b57')

    def test_light_custom_colors_have_readable_white_text(self):
        for value in ['#ffffff', '#ffff00', '#abcdef', '#1d4ed8']:
            color = readable_color(value)
            rgb = [int(color[i:i+2], 16) / 255 for i in (1, 3, 5)]
            channels = [v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4 for v in rgb]
            luminance = sum(v*w for v,w in zip(channels, [.2126,.7152,.0722]))
            self.assertGreaterEqual(1.05 / (luminance + .05), 4.5)
