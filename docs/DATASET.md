# Dataset and Knowledge Base

## Overview

This document describes the dataset and knowledge base used by the Mental Health Screening and Initial Assessment Agent.

---

## 1. Assessment Question Set

### 1.1 Structured Questions (6 Categories)

The agent uses a predefined set of structured questions aligned with common mental health screening practices.

| # | Category | Question | Purpose |
|---|----------|----------|---------|
| 1 | `mood` | How would you describe your mood and emotional wellbeing over the past 2 weeks? | Assess emotional state and mood patterns |
| 2 | `stress` | What are your current stress levels? What situations or factors contribute to your stress? | Identify stressors and stress management |
| 3 | `sleep` | How have you been sleeping? How many hours per night, and is your sleep restful? | Evaluate sleep quality and duration |
| 4 | `anxiety` | Have you experienced any anxiety symptoms? If so, please describe when and how they occur. | Detect anxiety symptoms and triggers |
| 5 | `daily_activities` | How are you managing your daily activities and responsibilities? | Assess functional capacity |
| 6 | `concerns` | What are your main concerns or challenges you'd like to discuss? | Open-ended concern collection |

### 1.2 Question Design Rationale

- **Time Frame:** "Past 2 weeks" aligns with PHQ-9 and GAD-7 standard screening tools
- **Open-Ended:** Allows individuals to express in their own words
- **Non-Leading:** Avoids suggesting specific answers
- **Comprehensive:** Covers key mental health domains

---

## 2. Distress Signal Knowledge Base

### 2.1 Severe Keywords (Immediate Review)

These keywords trigger `requires_immediate_review = True`:

```python
severe_keywords = [
    'suicide',
    'suicidal',
    'kill myself',
    'end my life',
    'self-harm'
]
```

### 2.2 Moderate Keywords (Review Required)

These keywords trigger `requires_review = True`:

```python
distress_keywords = [
    # Self-harm indicators
    'suicide', 'suicidal', 'kill myself', 'end my life',
    'self-harm', 'cut myself', 'hurt myself', 'die', 'death wish',

    # Severe distress
    'hopeless', "can't go on", 'no point', 'worthless',
    'hate myself', 'everyone would be better without me',
    'no reason to live',

    # Crisis indicators
    'plan to', 'going to hurt', 'want to die',
    "can't take it anymore"
]
```

### 2.3 Severity Classification

| Severity | Condition | Action |
|----------|-----------|--------|
| `high` | Any severe keyword found | Immediate professional review |
| `moderate` | Any distress keyword found | Professional review recommended |
| `low` | No keywords found | Standard processing |

---

## 3. Response Validation Rules

### 3.1 General Validation

| Rule | Threshold | Error/Warning |
|------|-----------|---------------|
| Minimum length | 3 characters | Error: "Response is too short" |
| Minimal responses | ok, fine, good, bad, yes, no, idk, dunno | Warning: "Response is quite brief" |

### 3.2 Category-Specific Validation

**Sleep Category:**
```python
sleep_keywords = ['hour', 'sleep', 'night', 'bed', 'wake', 'rest', 'insomnia']
# Warning if none present: "Consider mentioning sleep duration or quality"
```

**Mood Category:**
```python
emotion_keywords = ['feel', 'mood', 'emotion', 'happy', 'sad', 'angry', 'anxious', 'depressed']
# Warning if none present: "Consider describing your emotional state"
```

---

## 4. Synthetic Test Data

### 4.1 Test Scenario 1: Complete Assessment

```json
{
    "scenario": "complete_assessment",
    "responses": {
        "mood": "I've been feeling mostly okay. Some days are better than others. I feel happy when I spend time with my family but occasionally feel a bit down when work gets stressful.",
        "stress": "My stress is moderate. Work deadlines and financial responsibilities are the main factors. I try to manage it with exercise and hobbies.",
        "sleep": "I sleep about 6-7 hours per night. Sometimes I wake up in the middle of the night but generally feel rested in the morning.",
        "anxiety": "I occasionally feel nervous before important meetings. My heart races a bit but it passes quickly once I start talking.",
        "daily_activities": "I'm managing well overall. I keep a to-do list and try to stay organized. Some days I fall behind but I catch up on weekends.",
        "concerns": "I'd like to work on better work-life balance and managing my time more effectively."
    },
    "expected_outcome": {
        "status": "completed",
        "distress_detected": false,
        "flagged_for_professional": false
    }
}
```

### 4.2 Test Scenario 2: Missing Responses

```json
{
    "scenario": "missing_responses",
    "responses": {
        "mood": "I prefer not to discuss my emotions.",
        "stress": "I'd rather not say.",
        "sleep": "About 7 hours, generally restful."
    },
    "missing": ["anxiety", "daily_activities", "concerns"],
    "expected_outcome": {
        "status": "in_progress",
        "completion_percentage": 50,
        "missing_categories": ["anxiety", "daily_activities", "concerns"]
    }
}
```

### 4.3 Test Scenario 3: Conflicting Responses

```json
{
    "scenario": "conflicting_responses",
    "responses": {
        "mood": "I feel absolutely fantastic and extremely happy. Life couldn't be better.",
        "stress": "I'm under extreme, unbearable stress. I feel completely overwhelmed.",
        "sleep": "I sleep 10-12 hours every night and feel completely rested.",
        "anxiety": "I have constant severe panic attacks throughout the day.",
        "daily_activities": "I can't get out of bed most days. I've missed weeks of work.",
        "concerns": "I feel completely fine but everyone says I seem off."
    },
    "conflicts": [
        {"a": "mood", "b": "stress", "type": "contradictory"},
        {"a": "mood", "b": "daily_activities", "type": "contradictory"},
        {"a": "sleep", "b": "anxiety", "type": "inconsistent"}
    ],
    "expected_outcome": {
        "status": "requires_review",
        "flagged_for_professional": true,
        "reflection_issues": true
    }
}
```

### 4.4 Test Scenario 4: Distress Signals

```json
{
    "scenario": "distress_signals",
    "responses": {
        "mood": "I feel completely hopeless. Nothing makes me happy anymore and I feel worthless.",
        "stress": "Everything feels overwhelming. I can't take it anymore.",
        "sleep": "I barely sleep. I lie awake thinking about how there's no point in anything.",
        "anxiety": "Sometimes I think everyone would be better without me.",
        "daily_activities": "I can't do anything. I've stopped going to work.",
        "concerns": "I've been having thoughts of self-harm."
    },
    "detected_keywords": [
        "hopeless", "worthless", "can't take it anymore",
        "no point", "everyone would be better without me", "self-harm"
    ],
    "expected_outcome": {
        "status": "requires_review",
        "distress_detected": true,
        "flagged_for_professional": true,
        "severity": "high"
    }
}
```

### 4.5 Test Scenario 5: Interrupted Assessment

```json
{
    "scenario": "interrupted_assessment",
    "completed_responses": {
        "mood": "Feeling a bit anxious lately but managing day to day.",
        "stress": "Work has been demanding this month with tight deadlines."
    },
    "interruption_point": "After stress question",
    "expected_outcome": {
        "status": "in_progress",
        "responses_preserved": true,
        "resume_from": "sleep",
        "completion_percentage": 33
    }
}
```

---

## 5. LLM Prompts Knowledge Base

### 5.1 System Prompt

```
You are a compassionate mental health assessment assistant.
Your role is to conduct a structured initial assessment by asking questions
about mood, stress, sleep, anxiety, daily activities, and personal concerns.

Important guidelines:
- Be empathetic and supportive
- Never diagnose or provide treatment
- Ask one question at a time
- If you detect distress signals, acknowledge them compassionately
- Your goal is to collect information for a professional to review
```

### 5.2 Summary Generation Prompt

```
Based on the following assessment responses, create a structured summary
for a mental health professional.

Assessment Responses:
[RESPONSES]

Please provide:
1. A brief summary of reported concerns
2. Key observations about mood, stress, sleep, anxiety, and functioning
3. Any areas that may require immediate professional attention
4. Overall assessment completion status

Format the summary in a clear, professional manner.
```

### 5.3 Reflection/Validation Prompt

```
You are a quality reviewer for mental health assessment summaries.
Review the following summary against the original responses.

ORIGINAL RESPONSES:
[RESPONSES]

GENERATED SUMMARY:
[SUMMARY]

Evaluate the summary on these criteria:
1. ACCURACY: Does the summary accurately reflect what the person reported?
2. COMPLETENESS: Are the key points from each answered category addressed?
3. CRITICAL INFO: Is any critical information (especially distress indicators) captured?
4. TONE: Is the language professional and appropriate for clinical review?
5. NO FABRICATION: Does the summary avoid claiming specific facts not mentioned?

IMPORTANT:
- Minor clinical observations or professional language additions are ACCEPTABLE
- Only flag as invalid if there are MAJOR issues

Respond in this exact format:
VALID: [YES or NO]
ISSUES: [List specific issues if any, or "None" if valid]
SUGGESTIONS: [Brief suggestions for improvement, or "None" if valid]
```

---

## 6. Status Workflow States

### 6.1 Assessment Session Status

| Status | Description | Next Actions |
|--------|-------------|--------------|
| `pending` | Session created, not started | Start assessment |
| `in_progress` | Assessment ongoing | Continue answering |
| `completed` | All categories done, approved | View summary |
| `requires_review` | Needs professional review | Professional review |

### 6.2 Summary Completion Status

| Status | Description |
|--------|-------------|
| `complete` | All 6 categories answered |
| `partial` | Some categories answered |
| `incomplete` | Minimal responses |

---

## 7. Category Metadata

### 7.1 Display Names

```python
CATEGORY_DISPLAY_NAMES = {
    'mood': 'Mood & Emotional Wellbeing',
    'stress': 'Stress Levels',
    'sleep': 'Sleep Patterns',
    'anxiety': 'Anxiety Symptoms',
    'daily_activities': 'Daily Activities & Functioning',
    'concerns': 'Personal Concerns'
}
```

### 7.2 Category Order

The assessment follows this fixed order:
1. Mood
2. Stress
3. Sleep
4. Anxiety
5. Daily Activities
6. Concerns

---

## 8. Crisis Resources

### 8.1 Emergency Contacts (USA)

| Resource | Contact |
|----------|---------|
| National Suicide Prevention Lifeline | 988 |
| Crisis Text Line | Text HOME to 741741 |
| Emergency Services | 911 |
| SAMHSA National Helpline | 1-800-662-4357 |

### 8.2 International Resources

| Country | Resource | Contact |
|---------|----------|---------|
| UK | Samaritans | 116 123 |
| Canada | Crisis Services Canada | 1-833-456-4566 |
| Australia | Lifeline | 13 11 14 |

---

## 9. Data Privacy Considerations

### 9.1 Data Stored

| Data Type | Storage | Retention |
|-----------|---------|-----------|
| Session metadata | SQLite | Permanent |
| Question responses | SQLite | Permanent |
| AI summaries | SQLite | Permanent |
| LLM traces | LangSmith | Per LangSmith policy |

### 9.2 Data Not Stored

- User authentication credentials (none required)
- IP addresses
- Device information
- Cookies/tracking data

### 9.3 Compliance Notes

- System designed for professional use only
- No PHI identifiers stored by default
- User identifier is anonymized (session-based)
- Production deployment should implement proper security measures

---

**Document Version:** 1.0
**Last Updated:** November 2026
