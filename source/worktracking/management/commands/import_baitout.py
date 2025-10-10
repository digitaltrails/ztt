import csv
import re
from datetime import datetime
from decimal import Decimal
from typing import Dict

from django.core.management.base import BaseCommand
from django.db import transaction
from worktracking.models import (
    Outing, Line, TeamMember, Issue, CompletionStatus, IssueEnum, StationType
)

line_map: Dict[str, Line] = {}

def match_line_and_station(station_name: str) -> (int, Line):
    if not line_map:
        for line in Line.objects.all():
            line_map[str(line.name)] = line
    name_parts_match = re.match(r'^(.*?)([0-9]+)$', station_name)
    if name_parts_match:
        line_base_name = name_parts_match.group(1).strip()
        station_number = int(name_parts_match.group(2).strip())
        for line_base_name in (line_base_name, line_base_name.lower(), line_base_name + ' line'):
            for suffix in ('', ' east', ' west'):
                if line_record := line_map.get(line_base_name + suffix, None):
                    if int(line_record.start_station_id) <= station_number <= int(line_record.end_station_id):
                        return station_number, line_record
    return None, None

def match_station_type(issue_text: str) -> StationType:
    patterns = [(StationType.NOVACOIL_BOXED, r"NC.+box|box.+NC|black tunnel"),
                (StationType.NOVACOIL, r"NC|staple|[nN]ovacoil"),
                (StationType.WOODEN_BOX, r"box|screws"),
                ]
    for stn_type, pattern in patterns:
        if re.search(pattern, issue_text):
            return stn_type
    return StationType.NA

def match_issue_type(issue_text: str) -> IssueEnum:
    patterns = [(IssueEnum.ROPE_ON_DEAD_TREE, r"rope.+(dead|rott|tree)"),
                (IssueEnum.NEEDS_ROPE, r"rope"),
                (IssueEnum.MISSING_STATION, r"not found"),
                (IssueEnum.NEEDS_CLEARING, r"clear|mark|treefall|tree fall"),
                (IssueEnum.VERY_ROTTEN, r"rott"),
                (IssueEnum.RUSTING_HOOP, r"rust"),
                (IssueEnum.MISSING_HOOP, r'hoop'),
                (IssueEnum.NEEDS_NEW_ICC, r'IC|lid')
                ]
    for issue_type, pattern in patterns:
        if re.search(pattern, issue_text):
            return issue_type
    return IssueEnum.COMPLICATED

class Command(BaseCommand):
    help = 'Import outing data from TSV file'

    def add_arguments(self, parser):
        parser.add_argument('--commit', action='store_true', help='commit records to Issue table')
        parser.add_argument('--limit', type=int, help='commit records to Issue table', default=0)
        parser.add_argument('tag', type=str, help='origin tag for these issues')
        parser.add_argument('csv_file', type=str, help='Path to the CSV file')

    @transaction.atomic
    def handle(self, *args, **options):
        if commit := options['commit']:
            self.stdout.write(self.style.WARNING(f'Commiting data'))
        else:
            self.stdout.write(self.style.WARNING(f'Dry run only, rerun passing --commit to commit data'))

        tag = options['tag']
        csv_file = options['csv_file']

        limit = options['limit']
        if limit:
            self.stdout.write(self.style.WARNING(f'Limited to first {limit} rows'))

        created_count = 0

        with open(csv_file, 'r', encoding='utf-8') as file:
                
            reader = csv.reader(file, delimiter='|')
            
            for row_num, row in enumerate(reader):
                if limit and created_count > limit:
                    break
                if not row or len(row) < 2:
                    self.stdout.write(self.style.WARNING(f'Row {row_num}: skipped {len(row)} < 2'))
                    continue
                station_name = row[0].strip()
                station_number, line = match_line_and_station(station_name)

                try:
                    if line:
                        person = row[3].strip()
                        date = datetime.strptime(row[4].strip(), "%d/%m/%Y").date()
                        issue_text = row[6]
                        issue_type = match_issue_type(issue_text)
                        station_type = match_station_type(issue_text)
                        if options['commit']:
                            Issue.objects.create(
                                start_station_id=str(station_number),
                                end_station_id='',
                                station_type=station_type,
                                issue_type=issue_type,
                                description=issue_text,
                                line=line,
                                origin=tag,
                                reported_by=person
                            )
                        else:
                            self.stdout.write(f"{line.name=} {station_number=} {station_type=} {issue_type=} {tag=} {person=} {issue_text}")
                        created_count += 1
                        self.stdout.write(self.style.SUCCESS(f'Row {row_num}: Created issue for {line.name} on {date}'))
                    else:
                        self.stdout.write(self.style.ERROR(f'{row_num}: skipped failed to identify line for "{row[0]}"'))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'Row {row_num}: Error creating outing: {str(e)}'))
                    continue
        
        self.stdout.write(self.style.SUCCESS(f'Successfully imported baitout data, created {created_count} issues {commit=}.'))
