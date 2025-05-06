from django.core.management.base import BaseCommand
import random
import uuid
from django.utils import timezone
from datetime import timedelta
import os
from django.conf import settings
import numpy as np

from inventory.models import Regiment, Personnel, Weapon
from face_authentication.models import FaceRecord, AuthenticationLog, WeaponTransaction, FaceRegistrationLog


class Command(BaseCommand):
    help = 'Generates dummy data for testing the armory management system'

    def add_arguments(self, parser):
        parser.add_argument('--regiments', type=int, default=3, help='Number of regiments to create')
        parser.add_argument('--personnel', type=int, default=20, help='Number of personnel to create')
        parser.add_argument('--weapons', type=int, default=30, help='Number of weapons to create')
        parser.add_argument('--transactions', type=int, default=50, help='Number of transactions to create')
        parser.add_argument('--auth_logs', type=int, default=100, help='Number of authentication logs to create')
        parser.add_argument('--face_regs', type=int, default=15, help='Number of face registrations to create')
        parser.add_argument('--clear', action='store_true', help='Clear existing data before generating new data')

    def handle(self, *args, **options):
        if options['clear']:
            self.clear_data()
            self.stdout.write(self.style.SUCCESS('Data cleared successfully'))

        self.create_regiments(options['regiments'])
        self.create_personnel(options['personnel'])
        self.create_weapons(options['weapons'])
        self.create_transactions(options['transactions'])
        self.create_auth_logs(options['auth_logs'])
        self.create_face_registrations(options['face_regs'])

        self.stdout.write(self.style.SUCCESS('Test data generated successfully'))

    def clear_data(self):
        """Clear existing data from the database"""
        WeaponTransaction.objects.all().delete()
        AuthenticationLog.objects.all().delete()
        FaceRegistrationLog.objects.all().delete()
        FaceRecord.objects.all().delete()
        Weapon.objects.all().delete()
        Personnel.objects.all().delete()
        Regiment.objects.all().delete()

    def create_regiments(self, count):
        """Create regiment records"""
        regiment_types = [
            ('Танк', 'Танкын Баталион'),
            ('Артилери', 'Артилерийн Дивизион'),
            ('Мотобуудлага', 'Мотобуудлагын Баталион'),
        ]

        existing_count = Regiment.objects.count()
        for i in range(min(count, len(regiment_types))):
            regiment_id = f"{i+1:02d}"
            regiment_type = regiment_types[i][1]
            
            # Create only if it doesn't exist
            Regiment.objects.get_or_create(
                regiment_id=regiment_id,
                defaults={'regiment_type': regiment_type}
            )

        self.stdout.write(f'Created {Regiment.objects.count() - existing_count} regiments')

    def create_personnel(self, count):
        """Create personnel records"""
        ranks = ['Б/ч', 'А/б', 'Д/т', 'Т/ч', 'А/т']
        first_names = ['Бат', 'Болд', 'Ганбаатар', 'Дорж', 'Энх', 'Баяр', 'Сүхбаатар', 'Пүрэв', 'Мөнх', 'Гантулга']
        last_names = ['Батаа', 'Дорж', 'Гансүх', 'Хүрэл', 'Пүрэв', 'Ганбат', 'Цэрэн', 'Болд', 'Баяр', 'Баясгалан']

        regiments = list(Regiment.objects.all())
        if not regiments:
            self.stdout.write(self.style.ERROR('No regiments found. Create regiments first.'))
            return

        existing_count = Personnel.objects.count()
        for i in range(count):
            id_number = f"{i+101:03d}"
            
            # Skip if personnel with this ID already exists
            if Personnel.objects.filter(id_number=id_number).exists():
                continue
                
            first_name = random.choice(first_names)
            last_name = random.choice(last_names)
            rank = random.choice(ranks)
            regiment = random.choice(regiments)
            
            # Generate a random embedding
            fake_embedding = np.random.rand(512).astype(np.float32)
            embedding_bytes = fake_embedding.tobytes()
            
            personnel = Personnel.objects.create(
                id_number=id_number,
                first_name=first_name,
                last_name=last_name,
                rank=rank,
                regiment=regiment,
                face_encoding=embedding_bytes,
                active_status=random.random() > 0.1,  # 10% chance of being inactive
                registration_date=timezone.now() - timedelta(days=random.randint(0, 365))
            )
            
            # Also create a face record for this personnel
            FaceRecord.objects.create(
                personnel_id=id_number,
                face_embedding=embedding_bytes,
                registration_date=personnel.registration_date,
                is_active=personnel.active_status
            )

        self.stdout.write(f'Created {Personnel.objects.count() - existing_count} personnel records')

    def create_weapons(self, count):
        """Create weapon records"""
        models = ['АКМ', 'АКС', 'СВД', 'ПКТ']
        statuses = ['available', 'assigned', 'maintenance', 'decommissioned']
        locations = ['in', 'out']

        # Get all personnel
        personnel = list(Personnel.objects.filter(active_status=True))
        if not personnel:
            self.stdout.write(self.style.ERROR('No active personnel found. Create personnel first.'))
            return

        existing_count = Weapon.objects.count()
        for i in range(count):
            serial_number = f"S{i+1001:05d}"
            bolt_number = f"B{i+2001:05d}"
            case_number = f"C{i+3001:05d}"
            
            # Skip if weapon with this serial already exists
            if Weapon.objects.filter(serial_number=serial_number).exists():
                continue
                
            model = random.choice(models)
            status = random.choice(statuses)
            
            # For assigned weapons, set a personnel
            assigned_to = None
            if status == 'assigned':
                assigned_to = random.choice(personnel)
                
            location = random.choice(locations)
            if assigned_to and location == 'in':
                # If assigned but location is 'in', change to 'out' to be consistent
                location = 'out'
            
            Weapon.objects.create(
                serial_number=serial_number,
                bolt_number=bolt_number,
                case_number=case_number,
                weapon_model=model,
                status=status,
                assigned_to=assigned_to,
                acquisition_date=timezone.now() - timedelta(days=random.randint(30, 1000)),
                last_maintenance_date=timezone.now() - timedelta(days=random.randint(0, 180)) if random.random() > 0.3 else None,
                notes="Test weapon" if random.random() > 0.7 else "",
                location=location
            )

        self.stdout.write(f'Created {Weapon.objects.count() - existing_count} weapon records')

    def create_transactions(self, count):
        """Create weapon transaction records"""
        transaction_types = ['checkout', 'checkin', 'reassign']
        verifiers = ['Admin', 'System', 'OfficerDuty', 'CommandingOfficer']
        
        # Get all weapons and personnel
        weapons = list(Weapon.objects.all())
        personnel = list(Personnel.objects.filter(active_status=True))
        
        if not weapons or not personnel:
            self.stdout.write(self.style.ERROR('No weapons or personnel found. Create weapons and personnel first.'))
            return

        existing_count = WeaponTransaction.objects.count()
        for i in range(count):
            weapon = random.choice(weapons)
            person = random.choice(personnel)
            trans_type = random.choice(transaction_types)
            
            # Create a transaction
            transaction = WeaponTransaction.objects.create(
                id=uuid.uuid4(),
                weapon=weapon,
                personnel=person,
                transaction_type=trans_type,
                timestamp=timezone.now() - timedelta(days=random.randint(0, 90), 
                                                   hours=random.randint(0, 23),
                                                   minutes=random.randint(0, 59)),
                verified_by=random.choice(verifiers),
                notes="Тест" if random.random() > 0.7 else "",
                face_confidence_score=round(random.uniform(0.6, 0.99), 2) if random.random() > 0.2 else None
            )
            
            # Create an authentication log for this transaction
            auth_log = AuthenticationLog.objects.create(
                id=uuid.uuid4(),
                personnel_id=person.id_number,
                timestamp=transaction.timestamp,
                result='SUCCESS' if random.random() > 0.1 else random.choice(['FAILURE', 'ERROR']),
                confidence_score=transaction.face_confidence_score,
                ip_address=f"192.168.1.{random.randint(1, 254)}",
                device_info=f"User Agent: Test Browser {random.randint(1, 10)}"
            )
            
            # Link the auth log to the transaction
            transaction.auth_log = auth_log
            transaction.save()

        self.stdout.write(f'Created {WeaponTransaction.objects.count() - existing_count} weapon transactions')

    def create_auth_logs(self, count):
        """Create authentication log records"""
        results = ['SUCCESS', 'FAILURE', 'ERROR']
        
        # Get all personnel IDs
        personnel_ids = list(Personnel.objects.values_list('id_number', flat=True))
        
        if not personnel_ids:
            self.stdout.write(self.style.ERROR('No personnel found. Create personnel first.'))
            return

        existing_count = AuthenticationLog.objects.count()
        for i in range(count):
            personnel_id = random.choice(personnel_ids)
            result = random.choice(results)
            
            # Create an authentication log
            AuthenticationLog.objects.create(
                id=uuid.uuid4(),
                personnel_id=personnel_id,
                timestamp=timezone.now() - timedelta(days=random.randint(0, 30), 
                                                   hours=random.randint(0, 23),
                                                   minutes=random.randint(0, 59)),
                result=result,
                confidence_score=round(random.uniform(0.2, 0.99), 2) if result != 'ERROR' else None,
                ip_address=f"192.168.1.{random.randint(1, 254)}",
                device_info=f"User Agent: Test Browser {random.randint(1, 10)}",
                error_message="Test error message" if result == 'ERROR' else ""
            )

        self.stdout.write(f'Created {AuthenticationLog.objects.count() - existing_count} authentication logs')

    def create_face_registrations(self, count):
        """Create face registration log records"""
        registered_by = ['Admin', 'System', 'OfficerDuty', 'CommandingOfficer']
        
        # Get all personnel
        personnel = list(Personnel.objects.all())
        
        if not personnel:
            self.stdout.write(self.style.ERROR('No personnel found. Create personnel first.'))
            return

        existing_count = FaceRegistrationLog.objects.count()
        for i in range(count):
            person = random.choice(personnel)
            successful = random.random() > 0.1  # 10% chance of failure
            
            # Create a face registration log
            FaceRegistrationLog.objects.create(
                id=uuid.uuid4(),
                personnel=person,
                timestamp=timezone.now() - timedelta(days=random.randint(0, 90)),
                registered_by=random.choice(registered_by),
                successful=successful,
                error_message="" if successful else "Test error message"
            )

        self.stdout.write(f'Created {FaceRegistrationLog.objects.count() - existing_count} face registration logs')