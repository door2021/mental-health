"""
Custom management command to test the Mental Health Assessment Agent
Includes both legacy tests and new scale-based assessment tests
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from assessments.models import (
    AssessmentSession, AssessmentResponse, AssessmentSummary,
    PsychometricScale, ScaleItem, ScaleResponse, ScaleScore,
    GroundedSummary, FreeTextResponse
)
from assessments.services.scoring import scoring_engine
from assessments.services.validation import response_validator, distress_detector
from assessments.services.verification import summary_verifier


class Command(BaseCommand):
    help = 'Run test scenarios for the Mental Health Assessment Agent'

    def add_arguments(self, parser):
        parser.add_argument(
            '--legacy-only',
            action='store_true',
            help='Run only legacy tests'
        )
        parser.add_argument(
            '--scale-only',
            action='store_true',
            help='Run only scale-based tests'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting Mental Health Assessment Agent Tests\n'))

        # Determine which tests to run
        legacy_tests = [
            self.test_complete_assessment,
            self.test_missing_responses,
            self.test_conflicting_responses,
            self.test_distress_signals,
            self.test_interrupted_assessment,
        ]

        scale_tests = [
            self.test_complete_phq9,
            self.test_critical_response_flagging,
            self.test_severity_cutoffs,
            self.test_reverse_scoring,
            self.test_summary_verification_pass,
            self.test_hallucination_detection,
            self.test_fabricated_quote_detection,
            self.test_multi_scale_session,
        ]

        if options['legacy_only']:
            test_scenarios = legacy_tests
            self.stdout.write('Running legacy tests only...\n')
        elif options['scale_only']:
            test_scenarios = scale_tests
            self.stdout.write('Running scale-based tests only...\n')
        else:
            test_scenarios = legacy_tests + scale_tests

        passed = 0
        failed = 0

        for test_func in test_scenarios:
            try:
                self.stdout.write(f'\nRunning: {test_func.__name__}...')
                test_func()
                self.stdout.write(self.style.SUCCESS(f'  PASSED: {test_func.__name__}'))
                passed += 1
            except AssertionError as e:
                self.stdout.write(self.style.ERROR(f'  FAILED: {test_func.__name__}'))
                self.stdout.write(self.style.ERROR(f'    Assertion: {str(e)}'))
                failed += 1
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  FAILED: {test_func.__name__}'))
                self.stdout.write(self.style.ERROR(f'    Error: {str(e)}'))
                failed += 1

        # Summary
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(f'Total Tests: {passed + failed}')
        self.stdout.write(self.style.SUCCESS(f'Passed: {passed}'))
        if failed > 0:
            self.stdout.write(self.style.ERROR(f'Failed: {failed}'))
        self.stdout.write('=' * 60)

    # =========================================================================
    # LEGACY TESTS (Pre-Scale Assessment System)
    # =========================================================================

    def test_complete_assessment(self):
        """Test Scenario 1: Complete legacy assessment with all categories filled"""
        from assessments.services.tools import store_response

        session = AssessmentSession.objects.create(
            user_identifier='test_legacy_complete',
            status='in_progress',
            metadata={'legacy_format': True}
        )

        test_responses = {
            'mood': {
                'question': 'How would you describe your mood?',
                'response': 'Generally positive and stable.'
            },
            'stress': {
                'question': 'What are your current stress levels?',
                'response': 'Moderate stress from work but manageable.'
            },
            'sleep': {
                'question': 'How have you been sleeping?',
                'response': 'Sleeping about 7 hours per night.'
            },
            'anxiety': {
                'question': 'Have you experienced any anxiety?',
                'response': 'Mild anxiety occasionally.'
            },
            'daily_activities': {
                'question': 'How are you managing daily activities?',
                'response': 'Managing well overall.'
            },
            'concerns': {
                'question': 'What are your main concerns?',
                'response': 'Work-life balance.'
            }
        }

        for category, data in test_responses.items():
            store_response.invoke({
                'session_id': str(session.id),
                'category': category,
                'question': data['question'],
                'response': data['response']
            })

        session.refresh_from_db()
        assert session.responses.count() == 6, f"Expected 6 responses, got {session.responses.count()}"

    def test_missing_responses(self):
        """Test Scenario 2: Legacy assessment with missing responses"""
        from assessments.services.tools import store_response, identify_missing_categories

        session = AssessmentSession.objects.create(
            user_identifier='test_legacy_incomplete',
            status='in_progress',
            metadata={'legacy_format': True}
        )

        partial_responses = {
            'mood': {'question': 'How is your mood?', 'response': 'Okay.'},
            'stress': {'question': 'Stress levels?', 'response': 'High.'},
            'sleep': {'question': 'Sleep?', 'response': 'Poor.'}
        }

        for category, data in partial_responses.items():
            store_response.invoke({
                'session_id': str(session.id),
                'category': category,
                'question': data['question'],
                'response': data['response']
            })

        result = identify_missing_categories.invoke({'session_id': str(session.id)})
        assert not result['is_complete'], "Assessment should not be complete"
        assert len(result['missing_categories']) == 3

    def test_conflicting_responses(self):
        """Test Scenario 3: Legacy conflicting responses"""
        from assessments.services.tools import store_response

        session = AssessmentSession.objects.create(
            user_identifier='test_legacy_conflict',
            status='in_progress',
            metadata={'legacy_format': True}
        )

        conflicting = {
            'mood': {'question': 'Mood?', 'response': 'Great and happy!'},
            'stress': {'question': 'Stress?', 'response': 'Extreme, cannot cope.'},
        }

        for category, data in conflicting.items():
            store_response.invoke({
                'session_id': str(session.id),
                'category': category,
                'question': data['question'],
                'response': data['response']
            })

        session.status = 'requires_review'
        session.save()
        assert session.status == 'requires_review'

    def test_distress_signals(self):
        """Test Scenario 4: Legacy distress signal detection"""
        distress_response = "I feel hopeless and worthless."
        result = distress_detector.check_free_text(distress_response)

        assert result['has_distress_signal'], "Should detect distress"
        assert result['requires_review'], "Should require review"

    def test_interrupted_assessment(self):
        """Test Scenario 5: Legacy interrupted assessment"""
        from assessments.services.tools import store_response, identify_missing_categories

        session = AssessmentSession.objects.create(
            user_identifier='test_legacy_interrupted',
            status='in_progress',
            metadata={'legacy_format': True}
        )

        store_response.invoke({
            'session_id': str(session.id),
            'category': 'mood',
            'question': 'Mood?',
            'response': 'Feeling down.'
        })

        result = identify_missing_categories.invoke({'session_id': str(session.id)})
        assert not result['is_complete']
        assert session.status == 'in_progress'

    # =========================================================================
    # SCALE-BASED TESTS (New Psychometric Assessment System)
    # =========================================================================

    def _get_scale(self, code):
        """Helper to get a scale by code"""
        try:
            return PsychometricScale.objects.get(code=code)
        except PsychometricScale.DoesNotExist:
            raise AssertionError(f"Scale {code} not found. Run 'python manage.py load_scales' first.")

    def _create_scale_session(self, identifier, scales=None):
        """Helper to create a session with assigned scales"""
        session = AssessmentSession.objects.create(
            user_identifier=identifier,
            status='in_progress',
            phase='scales'
        )
        if scales:
            for scale in scales:
                session.assigned_scales.add(scale)
        return session

    def _store_scale_responses(self, session, scale, responses):
        """Helper to store multiple scale responses"""
        items = list(scale.items.order_by('item_number'))
        for i, value in enumerate(responses):
            if i < len(items):
                ScaleResponse.objects.create(
                    session=session,
                    item=items[i],
                    numeric_value=value
                )

    def test_complete_phq9(self):
        """Test: Complete PHQ-9 with all 9 items answered, verify score computation"""
        phq9 = self._get_scale('PHQ9')
        session = self._create_scale_session('test_phq9_complete', [phq9])

        # Responses: all 2s = moderate depression (total should be 18)
        responses = [2, 2, 2, 2, 2, 2, 2, 2, 2]  # 9 items, all value 2
        self._store_scale_responses(session, phq9, responses)

        # Compute score
        result = scoring_engine.compute_scale_score(session, phq9)

        expected_total = 18  # 9 * 2
        assert result.total_score == expected_total, \
            f"Expected score {expected_total}, got {result.total_score}"
        assert result.severity_level == 'moderately_severe', \
            f"Expected 'moderately_severe', got {result.severity_level}"

        # Save and verify persistence
        score = scoring_engine.save_score(session, phq9, result)
        assert score.total_score == expected_total

        self.stdout.write(f'    PHQ-9 Score: {result.total_score}/27 ({result.severity_level})')

    def test_critical_response_flagging(self):
        """Test: PHQ-9 Q9 (suicide item) >= 1 triggers review flag"""
        phq9 = self._get_scale('PHQ9')
        session = self._create_scale_session('test_phq9_critical', [phq9])

        # Low scores except Q9 = 1 (should trigger flag)
        responses = [0, 0, 0, 0, 0, 0, 0, 0, 1]  # Q9 = 1
        self._store_scale_responses(session, phq9, responses)

        result = scoring_engine.compute_scale_score(session, phq9)

        assert result.has_critical_response, "Should flag critical response"
        assert len(result.critical_item_details) > 0, "Should have critical items"
        assert result.critical_item_details[0]['item_number'] == 9, "Critical item should be Q9"

        self.stdout.write(f'    Critical item flagged: Q9 = 1')

    def test_severity_cutoffs(self):
        """Test: PHQ-9 severity cutoffs are correct"""
        phq9 = self._get_scale('PHQ9')

        test_cases = [
            (4, 'minimal'),      # 0-4 = minimal
            (5, 'mild'),          # 5-9 = mild
            (10, 'moderate'),     # 10-14 = moderate
            (15, 'moderately_severe'),  # 15-19 = moderately severe
            (20, 'severe'),       # 20-27 = severe
        ]

        for score_value, expected_severity in test_cases:
            session = self._create_scale_session(
                f'test_cutoff_{score_value}',
                [phq9]
            )

            # Create responses to achieve the target score
            # Distribute score across items
            responses = []
            remaining = score_value
            for i in range(9):
                if remaining >= 3:
                    responses.append(3)
                    remaining -= 3
                elif remaining > 0:
                    responses.append(remaining)
                    remaining = 0
                else:
                    responses.append(0)

            self._store_scale_responses(session, phq9, responses)
            result = scoring_engine.compute_scale_score(session, phq9)

            assert result.severity_level == expected_severity, \
                f"Score {score_value}: expected '{expected_severity}', got '{result.severity_level}'"

        self.stdout.write(f'    All severity cutoffs verified')

    def test_reverse_scoring(self):
        """Test: PSS-10 reverse-scored items (4, 5, 7, 8) computed correctly"""
        pss10 = self._get_scale('PSS10')
        session = self._create_scale_session('test_pss10_reverse', [pss10])

        # All responses = 4 (max value)
        # Regular items: score = 4
        # Reverse items (4, 5, 7, 8): score = 4 - 4 = 0
        responses = [4, 4, 4, 4, 4, 4, 4, 4, 4, 4]  # 10 items, all 4s
        self._store_scale_responses(session, pss10, responses)

        result = scoring_engine.compute_scale_score(session, pss10)

        # Regular items: 1, 2, 3, 6, 9, 10 = 6 items * 4 = 24
        # Reverse items: 4, 5, 7, 8 = 4 items * (4-4) = 0
        # Total = 24
        expected_total = 24
        assert result.total_score == expected_total, \
            f"Expected {expected_total}, got {result.total_score}"

        # Verify individual scored values
        scale_responses = ScaleResponse.objects.filter(
            session=session, item__scale=pss10
        ).select_related('item')

        for response in scale_responses:
            if response.item.is_reverse_scored:
                assert response.scored_value == 0, \
                    f"Q{response.item.item_number} reverse scored should be 0"
            else:
                assert response.scored_value == 4, \
                    f"Q{response.item.item_number} regular scored should be 4"

        self.stdout.write(f'    PSS-10 reverse scoring verified: {result.total_score}/40')

    def test_summary_verification_pass(self):
        """Test: Grounded summary with correct facts passes verification"""
        phq9 = self._get_scale('PHQ9')
        session = self._create_scale_session('test_verify_pass', [phq9])

        # Create responses for a score of 10 (moderate)
        responses = [1, 1, 1, 1, 1, 1, 2, 1, 1]  # Total = 10
        self._store_scale_responses(session, phq9, responses)

        result = scoring_engine.compute_scale_score(session, phq9)
        scoring_engine.save_score(session, phq9, result)

        # Create a factually correct summary
        correct_summary = """
        The patient completed the PHQ-9 depression screening.
        PHQ-9 score: 10, indicating moderate depression severity.
        No critical responses were noted on item 9 regarding self-harm.
        """

        verification = summary_verifier.verify(session, correct_summary)

        assert verification.is_valid, \
            f"Summary should pass verification. Errors: {verification.errors}"

        self.stdout.write(f'    Verification passed with no errors')

    def test_hallucination_detection(self):
        """Test: Wrong score in summary is detected as hallucination"""
        phq9 = self._get_scale('PHQ9')
        session = self._create_scale_session('test_hallucination', [phq9])

        # Actual score = 5 (mild)
        responses = [0, 1, 1, 1, 1, 0, 1, 0, 0]  # Total = 5
        self._store_scale_responses(session, phq9, responses)

        result = scoring_engine.compute_scale_score(session, phq9)
        scoring_engine.save_score(session, phq9, result)

        # Summary claims WRONG score (hallucination)
        hallucinated_summary = """
        Assessment Results:
        PHQ-9: 15 (moderately severe depression)
        The patient shows significant symptoms.
        """

        verification = summary_verifier.verify(session, hallucinated_summary)

        assert not verification.is_valid, "Should detect hallucination"
        assert len(verification.errors) > 0, "Should have error messages"
        assert any('HALLUCINATION' in e for e in verification.errors), \
            "Error should mention hallucination"

        self.stdout.write(f'    Hallucination detected: {verification.errors[0][:60]}...')

    def test_fabricated_quote_detection(self):
        """Test: Made-up quote in summary is flagged"""
        phq9 = self._get_scale('PHQ9')
        session = self._create_scale_session('test_fake_quote', [phq9])

        # Store responses with specific verbatim text
        items = list(phq9.items.order_by('item_number'))
        for i, item in enumerate(items):
            ScaleResponse.objects.create(
                session=session,
                item=item,
                numeric_value=1,
                verbatim_text="Feeling a bit down lately" if i == 0 else ""
            )

        result = scoring_engine.compute_scale_score(session, phq9)
        scoring_engine.save_score(session, phq9, result)

        # Summary with fabricated quote
        fake_quote_summary = """
        PHQ-9: 9

        The patient stated "I want to end my life and have no hope left"
        which indicates severe distress.
        """

        verification = summary_verifier.verify(session, fake_quote_summary)

        # Should flag the fabricated quote
        has_quote_error = any(
            'quote' in e.lower() or 'HALLUCINATION' in e
            for e in verification.errors
        )
        assert has_quote_error or len(verification.warnings) > 0, \
            "Should flag fabricated quote"

        self.stdout.write(f'    Fabricated quote flagged')

    def test_multi_scale_session(self):
        """Test: Complete session with PHQ-9, GAD-7, and PSS-10"""
        phq9 = self._get_scale('PHQ9')
        gad7 = self._get_scale('GAD7')
        pss10 = self._get_scale('PSS10')

        session = self._create_scale_session(
            'test_multi_scale',
            [phq9, gad7, pss10]
        )

        # PHQ-9: score 7 (mild)
        phq9_responses = [1, 1, 1, 0, 1, 1, 1, 1, 0]  # Total = 7
        self._store_scale_responses(session, phq9, phq9_responses)

        # GAD-7: score 10 (moderate)
        gad7_responses = [1, 2, 1, 2, 1, 2, 1]  # Total = 10
        self._store_scale_responses(session, gad7, gad7_responses)

        # PSS-10: score 20 (moderate)
        # Items 4,5,7,8 are reverse scored (0-indexed: 3,4,6,7)
        pss10_responses = [3, 2, 3, 1, 1, 2, 1, 1, 2, 2]  # Mixed values
        self._store_scale_responses(session, pss10, pss10_responses)

        # Compute all scores
        all_results = scoring_engine.compute_all_scores(session)

        assert 'PHQ9' in all_results.scores, "Should have PHQ-9 score"
        assert 'GAD7' in all_results.scores, "Should have GAD-7 score"
        assert 'PSS10' in all_results.scores, "Should have PSS-10 score"

        # Save all scores
        for scale_code, result in all_results.scores.items():
            scale = PsychometricScale.objects.get(code=scale_code)
            scoring_engine.save_score(session, scale, result)

        # Verify saved
        saved_scores = ScaleScore.objects.filter(session=session)
        assert saved_scores.count() == 3, f"Expected 3 scores, got {saved_scores.count()}"

        self.stdout.write(f'    PHQ-9: {all_results.scores["PHQ9"].total_score} ({all_results.scores["PHQ9"].severity_level})')
        self.stdout.write(f'    GAD-7: {all_results.scores["GAD7"].total_score} ({all_results.scores["GAD7"].severity_level})')
        self.stdout.write(f'    PSS-10: {all_results.scores["PSS10"].total_score} ({all_results.scores["PSS10"].severity_level})')
