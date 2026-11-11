from django.db import transaction

from apps.core.models import Sequence


def next_folio(prefix, name):
    with transaction.atomic():
        Sequence.objects.get_or_create(name=name, defaults={"value": 0})
        seq = Sequence.objects.select_for_update().get(name=name)
        seq.value += 1
        seq.save(update_fields=["value"])
        return f"{prefix}{seq.value:06d}"
