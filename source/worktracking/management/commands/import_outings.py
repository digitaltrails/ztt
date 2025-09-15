import csv
from datetime import datetime
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from worktracking.models import (
    Outing, Line, TeamMember, Issue, CompletionStatus, IssueEnum, StationType
)

class Command(BaseCommand):
    help = 'Import outing data from TSV file'

    def add_arguments(self, parser):
        parser.add_argument('tsv_file', type=str, help='Path to the TSV file')

    @transaction.atomic
    def handle(self, *args, **options):
        tsv_file = options['tsv_file']
        
        # Create a mapping from initials to TeamMember objects
        initials_map = {}
        
        with open(tsv_file, 'r', encoding='utf-8') as file:
            # Skip the header rows
            for _ in range(4):
                next(file)
                
            reader = csv.reader(file, delimiter='\t')
            
            for row_num, row in enumerate(reader, start=5):  # Start at 5 to account for header rows
                if not row or len(row) < 2:
                    continue
                    
                # Parse the row data
                date_str = row[0].strip()
                line_name = row[1].strip()
                
                # Skip rows without date or line name
                if not date_str or not line_name:
                    self.stdout.write(self.style.WARNING(f'Row {row_num}: Skipping - missing date or line name'))
                    continue
                    
                # Parse completion status
                status_text = row[2].strip() if len(row) > 2 and row[2] else ''
                if status_text == 'Completed':
                    completion_status = CompletionStatus.COMPLETED
                elif status_text == 'Partial':
                    completion_status = CompletionStatus.PARTIAL
                elif status_text == 'Tagged' or status_text == 'TaggedPart':
                    completion_status = CompletionStatus.PARTIAL  # Map tagged to partial
                else:
                    # Default to completed if not specified
                    completion_status = CompletionStatus.COMPLETED
                
                # Parse station range (subset of the line worked on)
                start_station = row[3].strip() if len(row) > 3 and row[3] else None
                end_station = row[4].strip() if len(row) > 4 and row[4] else None
                
                # Parse hours and workers (now allowing decimal values for workers)
                try:
                    hours = Decimal(row[5].strip()) if len(row) > 5 and row[5] else Decimal('0.0')
                except:
                    hours = Decimal('0.0')
                    
                try:
                    workers = Decimal(row[6].strip()) if len(row) > 6 and row[6] else Decimal('1.0')
                except:
                    workers = Decimal('1.0')
                
                # Parse notes (column 9)
                notes = row[9].strip() if len(row) > 9 and row[9] else ''
                
                # Parse participants (initials) - column 10 (after notes)
                who_initials = []
                if len(row) > 10 and row[10]:
                    who_initials = [init.strip() for init in row[10].split(',') if init.strip()]
                
                # Parse date
                try:
                    date = datetime.strptime(date_str, '%Y-%m-%d').date()
                except ValueError:
                    self.stdout.write(self.style.WARNING(f'Row {row_num}: Invalid date format: {date_str}'))
                    continue
                
                # Get or create the line
                try:
                    line = Line.objects.get(name=line_name)
                except Line.DoesNotExist:
                    self.stdout.write(self.style.WARNING(f'Row {row_num}: Line not found: {line_name}'))
                    continue
                
                # Create the outing
                try:
                    outing, created = Outing.objects.get_or_create(
                        date=date,
                        route=line,
                        defaults={
                            'completion_status': completion_status,
                            'start_station_id': start_station,
                            'end_station_id': end_station,
                            'hours': hours,
                            'number_of_workers': workers,
                        }
                    )
                    
                    if created:
                        self.stdout.write(self.style.SUCCESS(f'Row {row_num}: Created outing for {line_name} on {date}'))
                    else:
                        self.stdout.write(self.style.WARNING(f'Row {row_num}: Outing already exists for {line_name} on {date}'))
                    
                    # Handle participants
                    for initial in who_initials:
                        if initial not in initials_map:
                            # Create a team member for this initial if it doesn't exist
                            member, created = TeamMember.objects.get_or_create(
                                name=initial,
                                defaults={'email_address': f'{initial.lower()}@example.com'}
                            )
                            initials_map[initial] = member
                            if created:
                                self.stdout.write(self.style.SUCCESS(f'Created team member: {initial}'))
                        
                        # Add the team member to the outing
                        if initials_map[initial] not in outing.participants.all():
                            outing.participants.add(initials_map[initial])
                    
                    # Create an issue only if there are notes
                    if notes:
                        # Try to extract issue type from notes
                        issue_type = IssueEnum.COMPLICATED  # Default
                        for issue_choice in IssueEnum.choices:
                            if issue_choice[1].lower() in notes.lower():
                                issue_type = issue_choice[0]
                                break
                        
                        # Create the issue
                        Issue.objects.create(
                            start_station_id=start_station or '',
                            end_station_id=end_station,
                            simple_issue=issue_type,
                            station_type=StationType.NOVACOIL,  # Default
                            description=notes,
                            line=line,
                            outing=outing
                        )
                        self.stdout.write(self.style.SUCCESS(f'Row {row_num}: Created issue for {line_name} on {date}'))
                        
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'Row {row_num}: Error creating outing: {str(e)}'))
                    continue
        
        self.stdout.write(self.style.SUCCESS('Successfully imported outing data'))
