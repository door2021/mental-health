"""
Management command to load psychometric scale data from fixtures.

Usage:
    python manage.py load_scales
    python manage.py load_scales --clear  # Clear existing data first
"""
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.db import transaction


class Command(BaseCommand):
    help = 'Load psychometric scale definitions (PHQ-9, GAD-7, PSS-10, ISI)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing scale data before loading'
        )
        parser.add_argument(
            '--verify',
            action='store_true',
            help='Verify loaded data after loading'
        )

    def handle(self, *args, **options):
        from assessments.models import (
            PsychometricScale, ScaleItem, SeverityCutoff
        )

        if options['clear']:
            self.stdout.write('Clearing existing scale data...')
            SeverityCutoff.objects.all().delete()
            ScaleItem.objects.all().delete()
            PsychometricScale.objects.all().delete()
            self.stdout.write(self.style.SUCCESS('Existing data cleared.'))

        # Check if data already exists
        existing_scales = PsychometricScale.objects.count()
        if existing_scales > 0 and not options['clear']:
            self.stdout.write(
                self.style.WARNING(
                    f'Found {existing_scales} existing scales. '
                    f'Use --clear to replace them.'
                )
            )
            return

        self.stdout.write('Loading psychometric scale data...')

        try:
            with transaction.atomic():
                call_command(
                    'loaddata',
                    'assessments/fixtures/psychometric_scales.json',
                    verbosity=0
                )

            # Verify loaded data
            scales = PsychometricScale.objects.all()
            self.stdout.write(self.style.SUCCESS(f'\nLoaded {scales.count()} scales:'))

            for scale in scales:
                items = scale.items.count()
                cutoffs = scale.cutoffs.count()
                critical_items = scale.items.filter(is_critical=True).count()

                self.stdout.write(
                    f'  - {scale.code}: {scale.name}'
                )
                self.stdout.write(
                    f'    Items: {items}, Cutoffs: {cutoffs}, Critical items: {critical_items}'
                )

            if options['verify']:
                self._verify_data()

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error loading data: {str(e)}')
            )
            raise

    def _verify_data(self):
        """Verify that the loaded data is consistent"""
        from assessments.models import (
            PsychometricScale, ScaleItem, SeverityCutoff
        )

        self.stdout.write('\nVerifying loaded data...')
        errors = []

        # Verify each scale
        for scale in PsychometricScale.objects.all():
            # Check items are sequential
            items = list(scale.items.order_by('item_number'))
            expected_numbers = list(range(1, len(items) + 1))
            actual_numbers = [item.item_number for item in items]

            if actual_numbers != expected_numbers:
                errors.append(
                    f'{scale.code}: Item numbers not sequential. '
                    f'Expected {expected_numbers}, got {actual_numbers}'
                )

            # Check cutoffs cover the full range
            cutoffs = list(scale.cutoffs.order_by('min_score'))
            if cutoffs:
                # Check min starts at scale.min_score
                if cutoffs[0].min_score != scale.min_score:
                    errors.append(
                        f'{scale.code}: Cutoffs start at {cutoffs[0].min_score}, '
                        f'but scale min_score is {scale.min_score}'
                    )

                # Check max ends at scale.max_score
                if cutoffs[-1].max_score != scale.max_score:
                    errors.append(
                        f'{scale.code}: Cutoffs end at {cutoffs[-1].max_score}, '
                        f'but scale max_score is {scale.max_score}'
                    )

                # Check for gaps in cutoffs
                for i in range(len(cutoffs) - 1):
                    if cutoffs[i].max_score + 1 != cutoffs[i + 1].min_score:
                        errors.append(
                            f'{scale.code}: Gap in cutoffs between '
                            f'{cutoffs[i].max_score} and {cutoffs[i + 1].min_score}'
                        )

            # Check max_score calculation
            calculated_max = sum(item.max_value for item in items)
            if calculated_max != scale.max_score:
                errors.append(
                    f'{scale.code}: Calculated max score ({calculated_max}) '
                    f'does not match scale max_score ({scale.max_score})'
                )

            # Check response options are valid JSON
            for item in items:
                if not isinstance(item.response_options, list):
                    errors.append(
                        f'{scale.code} Q{item.item_number}: '
                        f'response_options is not a list'
                    )
                else:
                    for opt in item.response_options:
                        if 'value' not in opt or 'label' not in opt:
                            errors.append(
                                f'{scale.code} Q{item.item_number}: '
                                f'response_option missing value or label'
                            )

        if errors:
            self.stdout.write(self.style.ERROR('Verification failed:'))
            for error in errors:
                self.stdout.write(self.style.ERROR(f'  - {error}'))
        else:
            self.stdout.write(self.style.SUCCESS('All data verified successfully!'))

            # Print summary
            self.stdout.write('\nData Summary:')
            self.stdout.write(f'  Scales: {PsychometricScale.objects.count()}')
            self.stdout.write(f'  Items: {ScaleItem.objects.count()}')
            self.stdout.write(f'  Cutoffs: {SeverityCutoff.objects.count()}')
            self.stdout.write(
                f'  Critical items: {ScaleItem.objects.filter(is_critical=True).count()}'
            )
            self.stdout.write(
                f'  Reverse-scored items: {ScaleItem.objects.filter(is_reverse_scored=True).count()}'
            )
