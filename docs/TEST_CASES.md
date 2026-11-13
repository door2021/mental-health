# Test Cases - Mental Health Assessment Agent

## Overview

This document contains 5 comprehensive test scenarios with sample inputs and expected outputs for the Mental Health Screening and Initial Assessment Agent.

---

## Test Execution

```bash
# Run all test scenarios
python manage.py run_tests

# Run specific scenario
python manage.py run_tests --scenario 1
```

---

## Test Scenario 1: Complete Assessment

### Description
User completes all 6 assessment categories with valid responses.

### Input Data

| Category | Question | Sample Response |
|----------|----------|-----------------|
| Mood | How would you describe your mood and emotional wellbeing over the past 2 weeks? | I've been feeling mostly okay. Some days are better than others. I feel happy when I spend time with my family but occasionally feel a bit down when work gets stressful. |
| Stress | What are your current stress levels? What situations or factors contribute to your stress? | My stress is moderate. Work deadlines and financial responsibilities are the main factors. I try to manage it with exercise and hobbies on weekends. |
| Sleep | How have you been sleeping? How many hours per night, and is your sleep restful? | I sleep about 6-7 hours per night. Sometimes I wake up in the middle of the night but generally feel rested in the morning. |
| Anxiety | Have you experienced any anxiety symptoms? If so, please describe when and how they occur. | I occasionally feel nervous before important meetings. My heart races a bit but it passes quickly once I start talking. It's manageable. |
| Daily Activities | How are you managing your daily activities and responsibilities? | I'm managing well overall. I keep a to-do list and try to stay organized. Some days I fall behind but I catch up on weekends. |
| Concerns | What are your main concerns or challenges you'd like to discuss? | I'd like to work on better work-life balance and managing my time more effectively. Nothing urgent. |

### Expected Output

```json
{
    "session_status": "completed",
    "completion_percentage": 100,
    "missing_categories": [],
    "distress_detected": false,
    "flagged_for_professional": false,
    "summary_generated": true,
    "reflection_valid": true
}
```

### Sample Generated Summary

```markdown
## Assessment Summary

### Overview
The individual presents with generally stable mental health indicators.
Mood is described as variable but predominantly positive, with family
interactions serving as a source of happiness.

### Key Observations

**Mood & Emotional Wellbeing:**
- Generally okay with normal fluctuations
- Positive family relationships
- Work-related stress occasionally affects mood

**Stress Levels:**
- Moderate stress reported
- Primary stressors: work deadlines, financial responsibilities
- Healthy coping mechanisms in place (exercise, hobbies)

**Sleep Patterns:**
- 6-7 hours per night
- Occasional nighttime waking
- Generally feels rested

**Anxiety:**
- Mild situational anxiety (meetings)
- Physical symptoms present but manageable
- Quick recovery noted

**Daily Functioning:**
- Good organizational skills
- Uses productivity tools (to-do lists)
- Minor challenges with time management

**Reported Concerns:**
- Work-life balance improvement desired
- Time management skills
- No urgent concerns identified

### Areas for Professional Attention
- None requiring immediate attention
- General wellness discussion may be beneficial

### Assessment Status
✓ Complete - All categories addressed
✓ No distress signals detected
✓ Summary validated by reflection step
```

---

## Test Scenario 2: Missing Responses

### Description
User completes only 3 of 6 categories, leaving assessment incomplete.

### Input Data

| Category | Question | Sample Response |
|----------|----------|-----------------|
| Mood | How would you describe your mood... | I prefer not to discuss my emotions right now. |
| Stress | What are your current stress levels... | I'd rather not say. |
| Sleep | How have you been sleeping... | About 7 hours, generally restful. |
| Anxiety | *(Not answered - user leaves)* | — |
| Daily Activities | *(Not answered)* | — |
| Concerns | *(Not answered)* | — |

### Expected Output

```json
{
    "session_status": "in_progress",
    "completion_percentage": 50,
    "missing_categories": ["anxiety", "daily_activities", "concerns"],
    "distress_detected": false,
    "flagged_for_professional": false,
    "summary_generated": false,
    "reflection_valid": null
}
```

### System Behavior

```
identify_missing_categories() output:
{
    "status": "success",
    "completed_categories": ["mood", "stress", "sleep"],
    "missing_categories": ["anxiety", "daily_activities", "concerns"],
    "is_complete": false,
    "completion_percentage": 50
}
```

### Resume Capability Test

When user returns to `/assessment/<id>/`:

1. Previous responses are displayed
2. Chat resumes from next missing category (anxiety)
3. No data loss occurs

---

## Test Scenario 3: Conflicting Responses

### Description
User provides contradictory information across different categories.

### Input Data

| Category | Response | Conflict |
|----------|----------|----------|
| Mood | I feel **absolutely fantastic and extremely happy**. Life couldn't be better. I'm full of energy and joy every single day. | 😊 Very positive |
| Stress | I'm under **extreme, unbearable stress**. I feel completely overwhelmed and can barely function. Everything is falling apart. | 😰 Contradicts mood |
| Sleep | I sleep **10-12 hours** every night and feel completely rested. Best sleep of my life. | 😴 Unusually high |
| Anxiety | I have **constant severe panic attacks** throughout the day. My heart races, I can't breathe, and I feel like I'm dying multiple times daily. | 😨 Contradicts mood & sleep |
| Daily Activities | I **can't get out of bed** most days. I've missed weeks of work and stopped taking care of myself entirely. | 😞 Contradicts mood & sleep |
| Concerns | I'm worried because I feel **completely fine** but everyone around me says I seem off. I don't understand why. | 🤔 Denial pattern |

### Conflict Matrix

| Response A | Response B | Conflict Type |
|------------|------------|---------------|
| "Extremely happy" (mood) | "Unbearable stress" (stress) | Mood vs Stress |
| "Best sleep, 10-12 hours" | "Constant panic attacks" | Sleep vs Anxiety |
| "Full of energy" (mood) | "Can't get out of bed" (activities) | Energy vs Function |
| "Feel completely fine" | All negative responses | Denial vs Reality |

### Expected Output

```json
{
    "session_status": "requires_review",
    "completion_percentage": 100,
    "missing_categories": [],
    "distress_detected": false,
    "flagged_for_professional": true,
    "summary_generated": true,
    "reflection_valid": false,
    "reflection_issues": "Significant inconsistencies detected between reported mood and functional status"
}
```

### Sample Generated Summary (with flags)

```markdown
## Assessment Summary

### ⚠️ INCONSISTENCIES DETECTED

This assessment contains significant contradictions that require
professional evaluation:

### Conflicting Information

1. **Mood vs. Stress Discrepancy**
   - Reports: "absolutely fantastic and extremely happy"
   - Also reports: "extreme, unbearable stress"
   - These statements appear contradictory

2. **Sleep vs. Functioning Discrepancy**
   - Reports: 10-12 hours of restful sleep
   - Also reports: inability to get out of bed, missing work
   - Excessive sleep may indicate depressive symptoms

3. **Self-Perception Discrepancy**
   - Reports feeling "completely fine"
   - Others express concern about wellbeing
   - Possible lack of insight into own condition

### Areas Requiring Attention
- Inconsistent self-reporting patterns
- Possible denial or minimization
- Recommend in-depth clinical interview

### Reflection Issues
Reflection found issues: Significant inconsistencies between reported
emotional state and functional capacity require professional clarification.
```

---

## Test Scenario 4: Distress Signals

### Description
User provides responses containing crisis keywords that trigger immediate flagging.

### Input Data

| Category | Response | Distress Keywords |
|----------|----------|-------------------|
| Mood | I feel completely **hopeless**. Nothing makes me happy anymore and I feel **worthless** most of the time. | hopeless, worthless |
| Stress | Everything feels overwhelming. I **can't take it anymore**. Work, relationships, everything is falling apart. | can't take it anymore |
| Sleep | I barely sleep. Maybe 2-3 hours. I lie awake thinking about how there's **no point** in anything. | no point |
| Anxiety | Constant panic. I feel like I'm dying. Sometimes I think **everyone would be better without me**. | everyone would be better without me |
| Daily Activities | I can't do anything. I've stopped going to work. I don't eat. I just want everything to stop. | — |
| Concerns | I've been having thoughts of **self-harm**. I don't know what to do anymore. | self-harm |

### check_distress_signals() Output

```json
{
    "requires_immediate_review": true,
    "requires_review": true,
    "signals_found": [
        "hopeless",
        "worthless",
        "can't take it anymore",
        "no point",
        "everyone would be better without me",
        "self-harm"
    ],
    "severity": "high",
    "message": "URGENT: Immediate professional review required. Response contains crisis indicators."
}
```

### Expected Output

```json
{
    "session_status": "requires_review",
    "completion_percentage": 100,
    "missing_categories": [],
    "distress_detected": true,
    "flagged_for_professional": true,
    "summary_generated": true,
    "immediate_review_required": true
}
```

### System Behavior

1. **Immediate Flag:** Session status set to `requires_review` immediately
2. **Dashboard Alert:** Red badge displayed prominently
3. **Agent Response:**
   ```
   "Thank you for sharing. I've flagged this assessment for priority
   review by a mental health professional."
   ```
4. **Summary Contains:**
   - Crisis indicators section
   - Urgency flag
   - Recommendation for immediate professional contact

### Sample Summary (Flagged)

```markdown
## ⚠️ URGENT: Assessment Requires Immediate Professional Review

### Crisis Indicators Detected

The following concerning statements were identified:

- Expressions of hopelessness and worthlessness
- Statements suggesting inability to cope
- Thoughts that others would be better off without them
- **Self-harm ideation reported**

### Immediate Actions Required

1. Professional should contact individual promptly
2. Safety assessment recommended
3. Crisis resources should be provided

### Crisis Resources
- National Suicide Prevention Lifeline: 988
- Crisis Text Line: Text HOME to 741741
- Emergency Services: 911

### Assessment Details
[Full responses available for professional review]

---
**This assessment has been flagged for IMMEDIATE professional attention.**
```

---

## Test Scenario 5: Interrupted Assessment

### Description
User starts assessment but abandons session mid-way, testing state persistence and resume capability.

### Input Sequence

| Step | Action | State |
|------|--------|-------|
| 1 | Start new assessment | Session created, status: in_progress |
| 2 | Answer mood question | Response stored in database |
| 3 | Answer stress question | Response stored in database |
| 4 | **Close browser** | Session interrupted |
| 5 | *(Later)* Return to URL | Session should resume |

### Initial Responses

| Category | Response |
|----------|----------|
| Mood | Feeling a bit anxious lately but managing day to day. |
| Stress | Work has been demanding this month with tight deadlines. |

### State Before Interruption

```json
{
    "session_id": "12",
    "session_status": "in_progress",
    "completed_categories": ["mood", "stress"],
    "missing_categories": ["sleep", "anxiety", "daily_activities", "concerns"],
    "completion_percentage": 33,
    "responses_count": 2
}
```

### Expected Behavior on Return

1. **URL:** `/assessment/12/` remains accessible
2. **Conversation History:** Previous Q&A displayed
3. **Current Question:** Sleep question presented (next missing category)
4. **Data Integrity:** No responses lost

### Resume Verification

```python
# Verify state restoration
session = AssessmentSession.objects.get(id=12)
assert session.status == 'in_progress'
assert session.responses.count() == 2

missing = identify_missing_categories.invoke({'session_id': '12'})
assert missing['missing_categories'] == ['sleep', 'anxiety', 'daily_activities', 'concerns']
assert missing['completion_percentage'] == 33
```

### Expected UI on Resume

```
┌─────────────────────────────────────────────────┐
│ Assessment Session #12                          │
│ Status: in_progress                             │
├─────────────────────────────────────────────────┤
│                                                 │
│ AI: Hello! I'm here to help conduct a mental   │
│     health assessment...                        │
│                                                 │
│ AI: How would you describe your mood and       │
│     emotional wellbeing over the past 2 weeks? │
│                                                 │
│ You: Feeling a bit anxious lately but managing │
│      day to day.                               │
│                                                 │
│ AI: What are your current stress levels?       │
│                                                 │
│ You: Work has been demanding this month with   │
│      tight deadlines.                          │
│                                                 │
│ AI: How have you been sleeping? How many hours │
│     per night, and is your sleep restful?      │
│     ↑ RESUME POINT                             │
│                                                 │
│ [Type your response...]              [Send]    │
└─────────────────────────────────────────────────┘
```

---

## Validation Tools Output Reference

### store_response

```python
# Input
store_response.invoke({
    'session_id': '1',
    'category': 'mood',
    'question': 'How would you describe your mood...',
    'response': 'I feel generally happy and content.'
})

# Output
{
    'status': 'success',
    'message': 'Response stored for category: mood',
    'response_id': 42
}
```

### retrieve_responses

```python
# Input
retrieve_responses.invoke({'session_id': '1'})

# Output
{
    'status': 'success',
    'session_id': '1',
    'responses': {
        'mood': [
            {
                'question': 'How would you describe your mood...',
                'response': 'I feel generally happy and content.',
                'timestamp': '2026-11-13T10:30:00Z'
            }
        ],
        'stress': [...],
        ...
    },
    'total_responses': 6
}
```

### validate_response

```python
# Valid response
validate_response.invoke({
    'category': 'mood',
    'response': 'I feel happy and energetic most days.'
})
# Output: {'valid': True, 'errors': [], 'warnings': []}

# Invalid response (too short)
validate_response.invoke({
    'category': 'mood',
    'response': 'ok'
})
# Output: {
#     'valid': False,
#     'errors': [],
#     'warnings': ['Response is quite brief. More detail would be helpful.']
# }
```

### identify_missing_categories

```python
# Input
identify_missing_categories.invoke({'session_id': '1'})

# Output (partial completion)
{
    'status': 'success',
    'completed_categories': ['mood', 'stress', 'sleep'],
    'missing_categories': ['anxiety', 'daily_activities', 'concerns'],
    'is_complete': False,
    'completion_percentage': 50
}

# Output (complete)
{
    'status': 'success',
    'completed_categories': ['mood', 'stress', 'sleep', 'anxiety', 'daily_activities', 'concerns'],
    'missing_categories': [],
    'is_complete': True,
    'completion_percentage': 100
}
```

### check_distress_signals

```python
# No distress
check_distress_signals.invoke({
    'response_text': 'I feel good and am managing well.'
})
# Output: {
#     'requires_immediate_review': False,
#     'requires_review': False,
#     'signals_found': [],
#     'severity': 'low',
#     'message': 'No significant distress signals detected.'
# }

# Severe distress
check_distress_signals.invoke({
    'response_text': 'I have been thinking about self-harm lately.'
})
# Output: {
#     'requires_immediate_review': True,
#     'requires_review': True,
#     'signals_found': ['self-harm'],
#     'severity': 'high',
#     'message': 'URGENT: Immediate professional review required.'
# }
```

---

## Test Results Summary

| Scenario | Status | Notes |
|----------|--------|-------|
| 1. Complete Assessment | ✅ PASS | Summary generated, all categories complete |
| 2. Missing Responses | ✅ PASS | Missing categories identified correctly |
| 3. Conflicting Responses | ✅ PASS | Flagged for professional review |
| 4. Distress Signals | ✅ PASS | Immediate flagging triggered |
| 5. Interrupted Assessment | ✅ PASS | State preserved, resume working |

---

**Document Version:** 1.0
**Last Updated:** November 2026
