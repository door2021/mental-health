"""
Custom management command to test the Mental Health Assessment Agent
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from assessments.models import AssessmentSession, AssessmentResponse, AssessmentSummary
from assessments.services.agent_graph import assessment_graph, collect_response, check_completeness, ask_question, generate_summary, validate_summary, end_assessment
from assessments.services.tools import store_response, check_distress_signals


class Command(BaseCommand):
    help = 'Run test scenarios for the Mental Health Assessment Agent'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting Mental Health Assessment Agent Tests\n'))
        
        # Test scenarios
        test_scenarios = [
            self.test_complete_assessment,
            self.test_missing_responses,
            self.test_conflicting_responses,
            self.test_distress_signals,
            self.test_interrupted_assessment,
        ]
        
        passed = 0
        failed = 0
        
        for test_func in test_scenarios:
            try:
                self.stdout.write(f'\nRunning: {test_func.__name__}...')
                test_func()
                self.stdout.write(self.style.SUCCESS(f'✓ PASSED: {test_func.__name__}'))
                passed += 1
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'✗ FAILED: {test_func.__name__}'))
                self.stdout.write(self.style.ERROR(f'  Error: {str(e)}'))
                failed += 1
        
        # Summary
        self.stdout.write('\n' + '='*60)
        self.stdout.write(f'Total Tests: {passed + failed}')
        self.stdout.write(self.style.SUCCESS(f'Passed: {passed}'))
        if failed > 0:
            self.stdout.write(self.style.ERROR(f'Failed: {failed}'))
        self.stdout.write('='*60)

    def test_complete_assessment(self):
        """Test Scenario 1: Complete assessment with all categories filled"""
        self.stdout.write('  Creating complete assessment...')
        
        # Create session
        session = AssessmentSession.objects.create(
            user_identifier='test_user_complete',
            status='in_progress'
        )
        
        # Complete responses for all categories
        test_responses = {
            'mood': {
                'question': 'How would you describe your mood and emotional wellbeing over the past 2 weeks?',
                'response': 'I have been feeling generally positive and stable. Some ups and downs but overall good mood.'
            },
            'stress': {
                'question': 'What are your current stress levels?',
                'response': 'Moderate stress from work deadlines but manageable with regular breaks and exercise.'
            },
            'sleep': {
                'question': 'How have you been sleeping?',
                'response': 'Sleeping about 7 hours per night, mostly restful with occasional difficulty falling asleep.'
            },
            'anxiety': {
                'question': 'Have you experienced any anxiety symptoms?',
                'response': 'Mild anxiety before presentations at work but it passes quickly and does not interfere with daily life.'
            },
            'daily_activities': {
                'question': 'How are you managing your daily activities?',
                'response': 'Managing well, keeping up with work, exercise, and social activities without major issues.'
            },
            'concerns': {
                'question': 'What are your main concerns?',
                'response': 'Main concern is maintaining work-life balance as workload increases.'
            }
        }
        
        # Store all responses
        for category, data in test_responses.items():
            store_response.invoke({
                'session_id': str(session.id),
                'category': category,
                'question': data['question'],
                'response': data['response']
            })
        
        # Generate summary
        state = {
            'session_id': str(session.id),
            'is_complete': True,
            'requires_review': False,
            'distress_detected': False,
            'missing_categories': []
        }
        
        state = generate_summary(state)
        state = validate_summary(state)
        
        # Verify
        session.refresh_from_db()
        assert session.responses.count() == 6, f"Expected 6 responses, got {session.responses.count()}"
        assert hasattr(session, 'summary'), "Summary not created"
        assert session.summary.completion_status == 'complete', "Status should be complete"
        
        self.stdout.write(f'    Session ID: {session.id}')
        self.stdout.write(f'    Responses: {session.responses.count()}')
        self.stdout.write(f'    Status: {session.status}')

    def test_missing_responses(self):
        """Test Scenario 2: Assessment with missing responses"""
        self.stdout.write('  Creating assessment with missing responses...')
        
        session = AssessmentSession.objects.create(
            user_identifier='test_user_incomplete',
            status='in_progress'
        )
        
        # Only provide responses for some categories
        partial_responses = {
            'mood': {
                'question': 'How would you describe your mood?',
                'response': 'Feeling okay, some mood swings.'
            },
            'stress': {
                'question': 'What are your stress levels?',
                'response': 'High stress from multiple sources.'
            },
            'sleep': {
                'question': 'How have you been sleeping?',
                'response': 'Poor sleep, only 4-5 hours per night.'
            }
        }
        
        for category, data in partial_responses.items():
            store_response.invoke({
                'session_id': str(session.id),
                'category': category,
                'question': data['question'],
                'response': data['response']
            })
        
        # Check for missing categories
        from assessments.services.tools import identify_missing_categories
        result = identify_missing_categories.invoke({'session_id': str(session.id)})
        
        assert not result['is_complete'], "Assessment should not be complete"
        assert len(result['missing_categories']) == 3, f"Expected 3 missing, got {len(result['missing_categories'])}"
        
        # Generate partial summary
        state = {
            'session_id': str(session.id),
            'is_complete': False,
            'missing_categories': result['missing_categories'],
            'requires_review': False,
            'distress_detected': False
        }
        
        state = generate_summary(state)
        
        session.refresh_from_db()
        assert session.summary.completion_status == 'partial', "Status should be partial"
        
        self.stdout.write(f'    Session ID: {session.id}')
        self.stdout.write(f'    Missing: {result["missing_categories"]}')

    def test_conflicting_responses(self):
        """Test Scenario 3: Conflicting responses"""
        self.stdout.write('  Creating assessment with conflicting responses...')
        
        session = AssessmentSession.objects.create(
            user_identifier='test_user_conflict',
            status='in_progress'
        )
        
        # Responses that might conflict
        conflicting_responses = {
            'mood': {
                'question': 'How is your mood?',
                'response': 'I feel great and very happy all the time!'
            },
            'stress': {
                'question': 'Stress levels?',
                'response': 'Extreme stress, cannot cope, everything is overwhelming.'
            },
            'sleep': {
                'question': 'Sleep pattern?',
                'response': 'Sleeping 10-12 hours but still exhausted.'
            },
            'anxiety': {
                'question': 'Any anxiety?',
                'response': 'Severe panic attacks daily, avoiding social situations.'
            },
            'daily_activities': {
                'question': 'Daily functioning?',
                'response': 'Struggling to complete basic tasks, missing work frequently.'
            },
            'concerns': {
                'question': 'Main concerns?',
                'response': 'Everything feels wrong but also everything is perfect.'
            }
        }
        
        for category, data in conflicting_responses.items():
            store_response.invoke({
                'session_id': str(session.id),
                'category': category,
                'question': data['question'],
                'response': data['response']
            })
        
        state = {
            'session_id': str(session.id),
            'is_complete': True,
            'requires_review': True,
            'distress_detected': False,
            'missing_categories': []
        }
        
        state = generate_summary(state)
        
        session.refresh_from_db()
        assert session.status == 'requires_review', "Should require review for conflicting responses"
        
        self.stdout.write(f'    Session ID: {session.id}')
        self.stdout.write(f'    Status: {session.status}')

    def test_distress_signals(self):
        """Test Scenario 4: Responses indicating significant distress"""
        self.stdout.write('  Creating assessment with distress signals...')
        
        session = AssessmentSession.objects.create(
            user_identifier='test_user_distress',
            status='in_progress'
        )
        
        # Response with distress signals
        distress_response = "I feel hopeless and like there's no point in continuing. I hate myself and feel worthless."
        
        # Check for distress
        distress_check = check_distress_signals.invoke({'response_text': distress_response})
        
        assert distress_check['requires_review'], "Should detect distress signals"
        assert distress_check['severity'] in ['moderate', 'high'], "Should have moderate or high severity"
        
        # Store responses including the distressing one
        responses = {
            'mood': {
                'question': 'How is your mood?',
                'response': distress_response
            },
            'stress': {
                'question': 'Stress levels?',
                'response': 'Cannot handle any stress right now.'
            },
            'sleep': {
                'question': 'Sleep?',
                'response': 'Barely sleeping, maybe 2 hours a night.'
            },
            'anxiety': {
                'question': 'Anxiety?',
                'response': 'Constant anxiety and panic.'
            },
            'daily_activities': {
                'question': 'Daily activities?',
                'response': 'Cannot function, staying in bed most of the day.'
            },
            'concerns': {
                'question': 'Concerns?',
                'response': 'I do not see a way forward.'
            }
        }
        
        for category, data in responses.items():
            store_response.invoke({
                'session_id': str(session.id),
                'category': category,
                'question': data['question'],
                'response': data['response']
            })
        
        state = {
            'session_id': str(session.id),
            'is_complete': True,
            'requires_review': True,
            'distress_detected': True,
            'missing_categories': []
        }
        
        state = generate_summary(state)
        
        session.refresh_from_db()
        assert session.status == 'requires_review', "Should require professional review"
        assert session.summary.flagged_for_professional, "Should be flagged for professional"
        
        self.stdout.write(f'    Session ID: {session.id}')
        self.stdout.write(f'    Flagged: {session.summary.flagged_for_professional}')
        self.stdout.write(f'    Severity: {distress_check["severity"]}')

    def test_interrupted_assessment(self):
        """Test Scenario 5: Incomplete or interrupted assessment"""
        self.stdout.write('  Creating interrupted assessment...')
        
        session = AssessmentSession.objects.create(
            user_identifier='test_user_interrupted',
            status='in_progress'
        )
        
        # Start but don't finish
        interrupted_responses = {
            'mood': {
                'question': 'How is your mood?',
                'response': 'Feeling down lately.'
            },
            'stress': {
                'question': 'Stress levels?',
                'response': 'Very high stress.'
            }
        }
        
        for category, data in interrupted_responses.items():
            store_response.invoke({
                'session_id': str(session.id),
                'category': category,
                'question': data['question'],
                'response': data['response']
            })
        
        # Check state
        from assessments.services.tools import identify_missing_categories
        result = identify_missing_categories.invoke({'session_id': str(session.id)})
        
        assert not result['is_complete'], "Should not be complete"
        assert session.status == 'in_progress', "Should still be in progress"
        
        # Simulate resumption - add more responses
        session.status = 'in_progress'
        session.save()
        
        # Add remaining responses
        remaining = {
            'sleep': {
                'question': 'Sleep?',
                'response': 'About 6 hours, some interruptions.'
            },
            'anxiety': {
                'question': 'Anxiety?',
                'response': 'Some anxiety but manageable.'
            },
            'daily_activities': {
                'question': 'Daily activities?',
                'response': 'Getting things done but requires effort.'
            },
            'concerns': {
                'question': 'Concerns?',
                'response': 'Concerned about maintaining current pace.'
            }
        }
        
        for category, data in remaining.items():
            store_response.invoke({
                'session_id': str(session.id),
                'category': category,
                'question': data['question'],
                'response': data['response']
            })
        
        # Now complete
        result = identify_missing_categories.invoke({'session_id': str(session.id)})
        assert result['is_complete'], "Should now be complete"
        
        self.stdout.write(f'    Session ID: {session.id}')
        self.stdout.write(f'    Resumed and completed successfully')
