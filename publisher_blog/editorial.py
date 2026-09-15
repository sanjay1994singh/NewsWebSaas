"""Briefs only: never publish a calendar entry without a complete original article."""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from django.db import transaction
from django.utils.text import slugify
from .models import Post

IST = ZoneInfo('Asia/Kolkata')
SLOTS = ((8, 'hi'), (13, 'en'), (17, 'hi'), (20, 'en'))
TOPICS = [
    'Choosing News Starter, Plus, Pro and Professional',
    'Preparing a news website for a faster launch',
    'Custom domain and publication identity',
    'Planning monthly article capacity',
    'News Plus and evergreen explanatory blogs',
    'News Pro and YouTube video publishing',
    'News Professional and daily ePaper workflow',
    'Shorts and full video reports',
    'A practical onboarding checklist',
    'Monthly and longer subscription durations',
    'Planning an upgrade around newsroom workload',
    'Useful category navigation',
    'Accurate headlines and summaries',
    'Photo captions and accessible descriptions',
    'Mobile reading and page performance checks',
    'Corrections and source attribution',
    'Publishing schedules for small newsrooms',
    'Advertising and integration questions',
    'Measuring reader needs before adding features',
    'An accessible ePaper archive',
    'Proposed future feature: editorial approvals',
    'Proposed future feature: opt-in push notifications',
    'Proposed future feature: correction history',
    'Proposed future feature: backup restore dashboard',
    'Proposed future feature: multilingual assistance',
    'Proposed future feature: reader newsletters',
    'Proposed future feature: accessibility checks',
    'Proposed future feature: newsroom security controls',
    'Proposed future feature: paid reader access',
    'Proposed future feature: content exports',
    'Evaluating a news CMS demonstration',
    'Launching with a realistic editorial budget',
    'The first thirty days of reporting',
    'From social page to owned website',
    'Questions before buying a news website',
    'Included features and optional services',
    'A useful publisher contact page',
]
AUDIENCES = [
    'a solo reporter', 'a district publication', 'a Hindi newsroom',
    'a print newspaper', 'a video publisher', 'a community team',
    'an education publication', 'a sports newsroom', 'a business publication',
    'an established publisher',
]
ANGLES = ['a worked decision checklist', 'mistakes and a practical improvement plan']

@transaction.atomic
def seed_calendar(campaign):
    type(campaign).objects.select_for_update().get(pk=campaign.pk)
    created = 0
    for day in range(campaign.days):
        for slot, (hour, language) in enumerate(SLOTS):
            pair = day * 2 + slot // 2
            topic = TOPICS[pair % len(TOPICS)]
            audience = AUDIENCES[(pair // len(TOPICS)) % len(AUDIENCES)]
            angle = ANGLES[(pair // (len(TOPICS) * len(AUDIENCES))) % len(ANGLES)]
            scheduled = datetime.combine(campaign.starts_on + timedelta(days=day), time(hour), IST)
            _, added = Post.objects.get_or_create(campaign=campaign, scheduled_at=scheduled, defaults={
                'language': language, 'topic': f'{topic} for {audience}: {angle}',
                'slug': f'{slugify(topic)[:150]}-{campaign.pk}-{pair + 1}-{language}',
            })
            created += added
    return created

