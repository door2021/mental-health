# Mental Health Assessment Agent

An AI-powered mental health screening and initial assessment system built with **Django**, **LangGraph**, and **Groq AI**, featuring **standardized psychometric scales** and **hallucination safeguards**.

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org)
[![Django](https://img.shields.io/badge/Django-5.0+-green.svg)](https://www.djangoproject.com)
[![Groq](https://img.shields.io/badge/Groq-Llama_3.1-orange.svg)](https://groq.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Overview

This application helps mental health professionals conduct structured initial assessments using **validated psychometric instruments**:

- **PHQ-9** - Patient Health Questionnaire (Depression)
- **GAD-7** - Generalized Anxiety Disorder Scale
- **PSS-10** - Perceived Stress Scale
- **ISI** - Insomnia Severity Index

### Key Features

| Feature | Description |
|---------|-------------|
| **Validated Scales** | Standardized PHQ-9, GAD-7, PSS-10, ISI instruments |
| **Deterministic Scoring** | Algorithmic scoring with NO LLM in the scoring path |
| **Hallucination Prevention** | Fact-checking verifies LLM summaries against stored data |
| **Critical Item Detection** | Automatic flagging for items like PHQ-9 Q9 (suicidality) |
| **Professional Dashboard** | Review assessments, scores, and severity levels |
| **Human-in-the-Loop** | Professional review workflow for flagged cases |
| **Groq-Powered** | Fast AI summaries with Llama 3.1 (3-4x faster than GPT) |

**Important**: This system does NOT diagnose or treat mental health conditions. It only organizes self-reported information to support professional assessment.

---

## Architecture Overview

```
NEW SAFE ARCHITECTURE:
  User Response → Structured Likert Scale
                → Deterministic Scoring Algorithm (NO LLM)
                → Score-based Severity Classification
                → Verbatim Storage + Computed Scores
                → LLM assists ONLY with conversational flow
                → Grounded Summary (must cite verbatim quotes + scores)
                → Fact-Verification Layer (catches hallucinations)
                → Professional Review
```

---

## Quick Start

### 1. Navigate to Project

```bash
cd /Users/Projects/mental-health-assessment

# Activate virtual environment
source venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment

```bash
# Copy environment template
cp .env.example .env

# Edit .env and add your Groq API key
# GROQ_API_KEY=gsk_...
```

**Get Groq API Key (Free)**:
1. Visit [console.groq.com](https://console.groq.com)
2. Sign up for free account
3. Create API key
4. Add to `.env` file

### 4. Initialize Database

```bash
# Run migrations
python manage.py migrate

# Load psychometric scales
python manage.py load_scales --verify

# (Optional) Create admin user
python manage.py createsuperuser
```

### 5. Run the Application

```bash
# Start development server
python manage.py runserver

# Visit http://localhost:8000
```

### 6. Run Tests

```bash
# Run all 13 test scenarios (5 legacy + 8 scale-based)
python manage.py run_tests

# Run only scale-based tests
python manage.py run_tests --scale-only

# Run only legacy tests
python manage.py run_tests --legacy-only
```

---

## Psychometric Scales

### PHQ-9 (Patient Health Questionnaire-9)
- **Purpose**: Depression screening
- **Items**: 9 questions, 0-3 Likert scale
- **Score Range**: 0-27
- **Severity Cutoffs**:
  - 0-4: Minimal
  - 5-9: Mild
  - 10-14: Moderate
  - 15-19: Moderately Severe
  - 20-27: Severe
- **Critical Item**: Q9 (suicidality) - flags for review if >= 1

### GAD-7 (Generalized Anxiety Disorder-7)
- **Purpose**: Anxiety screening
- **Items**: 7 questions, 0-3 Likert scale
- **Score Range**: 0-21
- **Severity Cutoffs**:
  - 0-4: Minimal
  - 5-9: Mild
  - 10-14: Moderate
  - 15-21: Severe

### PSS-10 (Perceived Stress Scale-10)
- **Purpose**: Stress measurement
- **Items**: 10 questions, 0-4 Likert scale
- **Score Range**: 0-40
- **Reverse-Scored Items**: 4, 5, 7, 8
- **Severity Cutoffs**:
  - 0-13: Low Stress
  - 14-26: Moderate Stress
  - 27-40: High Stress

### ISI (Insomnia Severity Index)
- **Purpose**: Sleep disorder screening
- **Items**: 7 questions, 0-4 Likert scale
- **Score Range**: 0-28
- **Severity Cutoffs**:
  - 0-7: No Clinically Significant Insomnia
  - 8-14: Subthreshold Insomnia
  - 15-21: Clinical Insomnia (Moderate)
  - 22-28: Clinical Insomnia (Severe)

---

## Hallucination Prevention

The system includes a fact-checking layer to prevent LLM hallucinations:

### What Gets Verified
1. **Score Claims**: Checks if mentioned scores match database values
2. **Severity Claims**: Verifies severity level statements
3. **Quoted Text**: Confirms quotes exist in stored responses
4. **Invented Symptoms**: Warns about symptoms not measured by scales

### Example Verification
```python
# If LLM claims "PHQ-9: 15" but actual score is 10:
HALLUCINATION: Summary claims PHQ9 score is 15, but actual score is 10

# If LLM quotes text not in responses:
HALLUCINATION: Quote 'I want to end my life...' does not appear in any stored responses
```

---

## Project Structure

```
mental-health-assessment/
├── config/                        # Django project configuration
│   ├── settings.py               # Main settings
│   ├── urls.py                   # Root URL configuration
│   └── wsgi.py                   # WSGI application
│
├── assessments/                   # Main Django app
│   ├── models.py                 # Database models (10 models)
│   ├── views.py                  # View controllers
│   ├── urls.py                   # App URL patterns
│   ├── admin.py                  # Django admin configuration
│   │
│   ├── services/                 # Business logic
│   │   ├── agent_graph.py       # LangGraph state machine
│   │   ├── tools.py             # Agent tools (scale-aware)
│   │   ├── scoring.py           # Deterministic scoring engine
│   │   ├── validation.py        # Response validation
│   │   └── verification.py      # Hallucination detection
│   │
│   ├── fixtures/
│   │   └── psychometric_scales.json  # Scale definitions
│   │
│   ├── templates/assessments/    # HTML templates
│   │   ├── base.html
│   │   ├── dashboard.html
│   │   ├── assessment_form.html  # Likert UI
│   │   ├── summary_detail.html   # Score cards
│   │   └── review.html
│   │
│   └── management/commands/
│       ├── run_tests.py          # Test scenarios
│       └── load_scales.py        # Load scale fixtures
│
├── docs/                         # Documentation
│   ├── TECHNICAL_REPORT.md
│   ├── TEST_CASES.md
│   └── DATASET.md
│
├── db.sqlite3                    # SQLite database
├── requirements.txt              # Python dependencies
├── .env.example                  # Environment template
├── README.md                     # This file
├── ARCHITECTURE.md               # System architecture
└── CLAUDE.md                     # Development guide
```

---

## Database Models

### New Scale-Based Models

| Model | Purpose |
|-------|---------|
| `PsychometricScale` | Scale definitions (PHQ-9, GAD-7, etc.) |
| `ScaleItem` | Individual questions within scales |
| `SeverityCutoff` | Clinical cutoff points for scoring |
| `ScaleResponse` | User responses with numeric values |
| `ScaleScore` | Computed scores per scale |
| `FreeTextResponse` | Optional follow-up text responses |
| `GroundedSummary` | Verified AI summary with citations |

### Legacy Models (Preserved)

| Model | Purpose |
|-------|---------|
| `AssessmentSession` | Session tracking (updated with scale fields) |
| `AssessmentResponse` | Legacy free-text responses |
| `AssessmentSummary` | Legacy AI summaries |

---

## Test Scenarios

### Scale-Based Tests (8 tests)

| Test | Description |
|------|-------------|
| `test_complete_phq9` | All 9 items answered, score computed correctly |
| `test_critical_response_flagging` | PHQ-9 Q9 >= 1 triggers review flag |
| `test_severity_cutoffs` | Verify 5→mild, 10→moderate, 15→mod-severe, 20→severe |
| `test_reverse_scoring` | PSS-10 items 4,5,7,8 reversed correctly |
| `test_summary_verification_pass` | Grounded summary passes verification |
| `test_hallucination_detection` | Wrong score in summary is caught |
| `test_fabricated_quote_detection` | Made-up quote is flagged |
| `test_multi_scale_session` | Complete PHQ-9 + GAD-7 + PSS-10 session |

### Legacy Tests (5 tests)

| Test | Description |
|------|-------------|
| `test_complete_assessment` | All 6 categories filled, summary generated |
| `test_missing_responses` | Partial completion, identifies gaps |
| `test_conflicting_responses` | Inconsistent answers, flagged for review |
| `test_distress_signals` | Crisis keywords detected, immediate flag |
| `test_interrupted_assessment` | Resume capability testing |

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Dashboard view |
| GET | `/start/` | Start new assessment |
| GET | `/assessment/<id>/` | Chat interface (Likert UI) |
| POST | `/assessment/<id>/message/` | Send response (AJAX) |
| GET | `/summary/<id>/` | View summary with scores |
| GET | `/review/<id>/` | Professional review interface |
| POST | `/review/<id>/` | Approve/escalate |
| GET | `/admin/` | Django admin panel |

---

## Technology Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| **Backend** | Django | 5.2+ |
| **Agent** | LangGraph | 0.2+ |
| **LLM** | Groq (Llama 3.1 70B) | Latest |
| **Database** | SQLite (dev) / PostgreSQL (prod) | - |
| **Frontend** | Tailwind CSS | 3.x (CDN) |
| **Interactivity** | Alpine.js | 3.x (CDN) |
| **Orchestration** | LangChain | 0.3+ |

---

## Configuration

### Environment Variables (`.env`)

```bash
# Django Configuration
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Groq API Configuration
GROQ_API_KEY=your-groq-api-key-here

# LangSmith (Optional)
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your-langsmith-key
LANGCHAIN_PROJECT=mental-health-assessment
```

---

## Usage

### For End Users

1. Visit dashboard at http://localhost:8000
2. Click **"New Assessment"** to start
3. Answer Likert scale questions by clicking response buttons
4. Complete all scales (PHQ-9, GAD-7, PSS-10, ISI)
5. Optionally provide additional context in follow-up
6. View your assessment summary

### For Professionals

1. Access dashboard to see all assessments
2. Review flagged assessments (red badge: **Requires Review**)
3. View detailed scores, severity levels, and critical items
4. Check verification status (hallucination detection results)
5. Approve or escalate using the review interface
6. Access admin panel at http://localhost:8000/admin

---

## Security & Safety

### Built-in Safety Features

- Deterministic scoring (no LLM can alter scores)
- Hallucination prevention (fact-checking layer)
- Critical item detection (PHQ-9 Q9 auto-flags)
- Professional review workflow
- Verbatim quote verification
- No diagnosis or treatment provided

### Production Checklist

- [ ] Set `DEBUG=False`
- [ ] Configure `ALLOWED_HOSTS`
- [ ] Use strong `SECRET_KEY`
- [ ] Enable HTTPS
- [ ] Use PostgreSQL
- [ ] Configure rate limiting
- [ ] Set up monitoring

---

## Documentation

| Document | Purpose |
|----------|---------|
| **README.md** | Quick start guide (this file) |
| **ARCHITECTURE.md** | System architecture & diagrams |
| **CLAUDE.md** | Development guide |
| **docs/TECHNICAL_REPORT.md** | Formal technical report |
| **docs/TEST_CASES.md** | Test scenarios with samples |
| **docs/DATASET.md** | Dataset and scale documentation |

---

## Troubleshooting

### Common Issues

**"Scale not found" error**
```bash
python manage.py load_scales --verify
```

**"Module not found: langchain_groq"**
```bash
source venv/bin/activate
pip install -r requirements.txt
```

**"GROQ_API_KEY not set"**
```bash
cp .env.example .env
# Edit .env and add your API key
```

---

## Disclaimer

**This system is for professional use only.** It does not diagnose, treat, or provide medical advice. Always consult qualified mental health professionals for diagnosis and treatment.

If you or someone you know is in crisis:
- **National Suicide Prevention Lifeline**: 988
- **Crisis Text Line**: Text HOME to 741741
- **Emergency Services**: 911

---

## Get Started

```bash
# 1. Navigate to project
cd /Users/Projects/mental-health-assessment

# 2. Activate environment
source venv/bin/activate

# 3. Configure
cp .env.example .env
# Edit .env with your GROQ_API_KEY

# 4. Initialize
python manage.py migrate
python manage.py load_scales --verify

# 5. Run
python manage.py runserver

# 6. Visit http://localhost:8000
```

---

**Built with Django, LangChain, LangGraph, and Groq AI**

For detailed documentation, see [ARCHITECTURE.md](ARCHITECTURE.md)
