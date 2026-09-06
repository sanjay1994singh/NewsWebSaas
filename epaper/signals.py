from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import EPaperEdition, EPaperPage


def remove_files(instance, names):
    for name in names:
        field = getattr(instance, name)
        if field and field.name:
            storage, path = field.storage, field.name
            transaction.on_commit(lambda storage=storage, path=path: storage.delete(path))


@receiver(post_delete, sender=EPaperPage)
def remove_page_media(sender, instance, **kwargs):
    remove_files(instance, ('image', 'mobile_image', 'zoom_image', 'thumbnail'))


@receiver(post_delete, sender=EPaperEdition)
def remove_edition_media(sender, instance, **kwargs):
    remove_files(instance, ('pdf_file', 'cover_image'))
