# your_app/management/commands/update_names.py
from django.core.management.base import BaseCommand
from worktracking.models import (
    Line
)

class Command(BaseCommand):
    help = 'Replaces spaces with hyphens in the "name" column of Line'

    def handle(self, *args, **kwargs):
        updated_count = 0
        for instance in Line.objects.all():
            old_name = instance.name
            new_name = old_name.replace("-", " ")
            if old_name != new_name:
                instance.name = new_name
                instance.save()
                updated_count += 1
        self.stdout.write(self.style.SUCCESS(f'Successfully updated {updated_count} names.'))
