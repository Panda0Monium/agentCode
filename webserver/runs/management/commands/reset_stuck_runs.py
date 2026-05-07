from django.core.management.base import BaseCommand
from django.utils import timezone

from runs.models import Run


class Command(BaseCommand):
    help = 'Mark any RUNNING runs as FAILED — use after an unexpected worker crash.'

    def handle(self, *args, **options):
        stuck = Run.objects.filter(status=Run.Status.RUNNING)
        count = stuck.count()

        if not count:
            self.stdout.write('No stuck runs found.')
            return

        stuck.update(
            status=Run.Status.FAILED,
            error='Worker was shut down or crashed while this run was in progress.',
            completed_at=timezone.now(),
        )
        self.stdout.write(self.style.WARNING(f'Reset {count} stuck run(s) to FAILED.'))
