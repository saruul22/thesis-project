from django.core.management.base import BaseCommand
from inventory.models import Personnel
import csv
import os

class Command(BaseCommand):
    help = 'Import personnel from CSV file'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='Path to CSV file')

    def handle(self, *args, **options):
        csv_file = options['csv_file']
        if not os.path.exists(csv_file):
            self.stdout.write(self.style.ERROR(f'File "{csv_file}" does not exist'))
            return

        with open(csv_file, 'r') as file:
            csv_reader = csv.DictReader(file)
            for row in csv_reader:
                try:
                    # Create or update personnel
                    personnel, created = Personnel.objects.update_or_create(
                        id_number=row.get('id_number', ''),
                        defaults={
                            'first_name': row.get('first_name', ''),
                            'last_name': row.get('last_name', ''),
                            'rank': row.get('rank', ''),
                            'unit': row.get('unit', ''),
                            'active_status': row.get('active', 'True').lower() in ('true', 'yes', '1'),
                        }
                    )
                    
                    action = 'Created' if created else 'Updated'
                    self.stdout.write(self.style.SUCCESS(f'{action} personnel: {personnel}'))
                    
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'Error processing row {row}: {e}'))