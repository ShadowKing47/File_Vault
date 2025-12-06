"""
Management command to trigger storage maintenance tasks manually.
"""
from django.core.management.base import BaseCommand
from data.tasks import (
    check_all_chunk_replication,
    garbage_collect_orphaned_chunks,
    storage_node_health_check,
    verify_chunk_integrity
)


class Command(BaseCommand):
    help = 'Run storage maintenance tasks (replication check, garbage collection, health check)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--task',
            type=str,
            choices=['replication', 'garbage', 'health', 'all'],
            default='all',
            help='Which maintenance task to run'
        )
        parser.add_argument(
            '--async',
            action='store_true',
            help='Run tasks asynchronously via Celery (default: synchronous)'
        )

    def handle(self, *args, **options):
        task_type = options['task']
        run_async = options['async']

        if run_async:
            self.stdout.write(self.style.WARNING('Running tasks asynchronously via Celery...'))
        else:
            self.stdout.write(self.style.WARNING('Running tasks synchronously...'))

        if task_type in ['replication', 'all']:
            self.stdout.write('Starting replication check...')
            if run_async:
                result = check_all_chunk_replication.delay()
                self.stdout.write(self.style.SUCCESS(f'Replication task queued: {result.id}'))
            else:
                result = check_all_chunk_replication()
                self.stdout.write(self.style.SUCCESS(f'Replication check completed: {result}'))

        if task_type in ['garbage', 'all']:
            self.stdout.write('Starting garbage collection...')
            if run_async:
                result = garbage_collect_orphaned_chunks.delay()
                self.stdout.write(self.style.SUCCESS(f'Garbage collection task queued: {result.id}'))
            else:
                result = garbage_collect_orphaned_chunks()
                self.stdout.write(self.style.SUCCESS(f'Garbage collection completed: {result}'))

        if task_type in ['health', 'all']:
            self.stdout.write('Starting health check...')
            if run_async:
                result = storage_node_health_check.delay()
                self.stdout.write(self.style.SUCCESS(f'Health check task queued: {result.id}'))
            else:
                result = storage_node_health_check()
                self.stdout.write(self.style.SUCCESS(f'Health check completed: {result}'))

        self.stdout.write(self.style.SUCCESS('All requested tasks completed!'))
