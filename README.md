# Mental Health Assessment Agent

An AI-powered mental health screening and initial assessment system built with **Django**, **LangGraph**, and **Groq AI**.

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org)
[![Django](https://img.shields.io/badge/Django-5.0+-green.svg)](https://www.djangoproject.com)
[![Groq](https://img.shields.io/badge/Groq-Llama_3.1-orange.svg)](https://groq.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 🎯 Overview

This application helps mental health professionals conduct structured initial assessments by:
- ✅ Collecting information about **mood, stress, sleep, anxiety, daily activities**, and **concerns**
- ✅ Validating responses and identifying missing information
- ✅ Detecting distress signals that require immediate attention
- ✅ Generating **AI-powered summaries** using Groq's Llama 3.1 70B
- ✅ Providing a **human-in-the-loop** approval workflow

**⚠️ Important**: This system does NOT diagnose or treat mental health conditions. It only organizes self-reported information to support professional assessment.

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 💬 **Interactive Chat** | Real-time conversation using Tailwind CSS & Alpine.js |
| 🤖 **LangGraph Agent** | State-based workflow with conditional routing |
| 🛠️ **5 Functional Tools** | Store, retrieve, validate, identify gaps, detect distress |
| 📊 **Professional Dashboard** | Review assessments, view summaries, approve/escalate |
| 🚨 **Safety Mechanisms** | Automatic flagging of concerning responses |
| 💾 **Resume Capability** | Interrupted assessments can be continued later |
| ⚡ **Groq-Powered** | Fast AI summaries with Llama 3.1 70B (3-4x faster than GPT) |

---

## 🚀 Quick Start

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

# (Optional) Create admin user
python manage.py createsuperuser
```

### 5. Run the Application

```bash
# Start development server
python manage.py runserver

# Visit http://localhost:8000
```

### 6. (Optional) Run Tests

```bash
# Test all 5 scenarios
python manage.py run_tests

# Verify setup
python verify_setup.py
```

---

## 📁 Project Structure

```
mental-health-assessment/        # Root project directory
├── config/                     # Django project configuration
│   ├── settings.py            # Main settings (uses GROQ_API_KEY)
│   ├── urls.py                # Root URL configuration
│   └── wsgi.py                # WSGI application
│
├── assessments/               # Main Django app
│   ├── models.py             # Database models (Session, Response, Summary)
│   ├── views.py              # View controllers
│   ├── urls.py               # App URL patterns
│   ├── admin.py              # Django admin configuration
│   │
│   ├── services/             # LangGraph agent
│   │   ├── agent_graph.py   # State machine with Groq
│   │   └── tools.py         # 5 functional tools
│   │
│   ├── templates/
│   │   └── assessments/     # HTML templates
│   │       ├── base.html
│   │       ├── dashboard.html
│   │       ├── assessment_form.html
│   │       ├── summary_detail.html
│   │       └── review.html
│   │
│   └── management/
│       └── commands/
│           └── run_tests.py  # Test scenarios
│
├── db.sqlite3                # SQLite database (permanent storage)
├── requirements.txt          # Python dependencies
├── .env.example             # Environment variable template
├── manage.py                # Django management script
├── verify_setup.py          # Setup verification
│
└── Documentation/
    ├── README.md            # This file
    ├── ARCHITECTURE.md      # Detailed architecture docs
    ├── MIGRATION_GUIDE.md   # Migration & changes guide
    ├── CLAUDE.md            # Development guide
    └── IMPLEMENTATION_SUMMARY.md
```

---

## 🏗️ Technology Stack

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

## 🧪 Test Scenarios

The system includes 5 comprehensive test scenarios:

| # | Scenario | Description |
|---|----------|-------------|
| 1 | ✅ **Complete Assessment** | All categories filled, summary generated |
| 2 | 📝 **Missing Responses** | Partial completion, identifies gaps |
| 3 | ⚠️ **Conflicting Responses** | Inconsistent answers, flagged for review |
| 4 | 🚨 **Distress Signals** | Crisis keywords detected, immediate flag |
| 5 | 🔄 **Interrupted Assessment** | Resume capability testing |

Run with:
```bash
python manage.py run_tests
```

---

## 📚 Usage

### For End Users

1. Visit dashboard at http://localhost:8000
2. Click **"New Assessment"** to start
3. Answer questions honestly in the chat interface
4. Receive confirmation when complete

### For Professionals

1. Access dashboard to see all assessments
2. Review flagged assessments (red badge: **Requires Review**)
3. View detailed summaries and responses
4. Approve or escalate using the review interface
5. Access admin panel at http://localhost:8000/admin

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Dashboard view |
| GET | `/start/` | Start new assessment |
| GET | `/assessment/<id>/` | Chat interface |
| POST | `/assessment/<id>/message/` | Send message (AJAX) |
| GET | `/summary/<id>/` | View summary |
| GET | `/review/<id>/` | Review interface |
| POST | `/review/<id>/` | Approve/escalate |
| GET | `/admin/` | Django admin panel |

---

## ⚙️ Configuration

### Environment Variables (`.env`)

```bash
# Django Configuration
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Groq API Configuration
GROQ_API_KEY=your-groq-api-key-here
```

### Database Configuration

**Development** (default):
```python
# SQLite - file-based database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}
```

**Production** (recommended):
```python
# PostgreSQL - production database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'mental_health_db',
        'USER': 'postgres',
        'PASSWORD': 'your_password',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}
```

---

## 🧠 How It Works

### Persistence Architecture

The system uses **two types of persistence**:

#### 1. SQLite Database - **Permanent Storage**
- Stores all assessment data permanently
- Models: `AssessmentSession`, `AssessmentResponse`, `AssessmentSummary`
- Survives server restarts
- Used by Django ORM, views, admin

#### 2. MemorySaver - **Temporary State**
- LangGraph workflow state management
- Temporary conversation flow
- Cleared on server restart
- Used by agent during execution only

**They serve different purposes** - both are needed!

### LangGraph Workflow

```
User Input
    ↓
start_assessment (Initialize)
    ↓
ask_question (Present question)
    ↓
collect_response (Store & validate)
    ↓
check_completeness (All categories?)
    ↓         ↓
   NO       YES
    ↓         ↓
ask_question  generate_summary (Groq AI)
    ↓
validate_summary (Quality check)
    ↓
end_assessment (Finalize)
    ↓
Display to User
```

### Agent Tools

1. **store_response**: Save to database
2. **retrieve_responses**: Get all responses
3. **validate_response**: Check quality
4. **identify_missing_categories**: Find gaps
5. **check_distress_signals**: Detect concerning content

---

## 🛠️ Development

### Making Changes

**Models** (after editing `models.py`):
```bash
python manage.py makemigrations
python manage.py migrate
```

**Templates** (no restart needed in DEBUG mode):
- Just reload your browser

**Views/Settings** (requires restart):
```bash
# Stop server (Ctrl+C)
python manage.py runserver
```

### Database Operations

```bash
# Create migrations
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Reset database
rm db.sqlite3
python manage.py migrate

# Create superuser for admin
python manage.py createsuperuser

# Django shell for testing
python manage.py shell
```

---

## 🔒 Security & Safety

### Built-in Safety Features
- ✅ No diagnosis or treatment provided
- ✅ Distress signal detection with keyword matching
- ✅ Professional review required for flagged cases
- ✅ All responses stored securely
- ✅ CSRF protection enabled
- ✅ Environment-based configuration

### Production Security Checklist
- [ ] Set `DEBUG=False`
- [ ] Configure `ALLOWED_HOSTS` properly
- [ ] Use strong `SECRET_KEY` (64+ random chars)
- [ ] Enable HTTPS only (`SECURE_SSL_REDIRECT`)
- [ ] Set secure cookie flags
- [ ] Configure CORS headers
- [ ] Add rate limiting
- [ ] Set up logging and monitoring
- [ ] Use PostgreSQL instead of SQLite
- [ ] Configure static file serving

---

## 📖 Documentation

| Document | Purpose |
|----------|---------|
| **README.md** (this file) | Quick start guide |
| **ARCHITECTURE.md** | Detailed architecture & design |
| **MIGRATION_GUIDE.md** | Changes summary & migration |
| **CLAUDE.md** | Development guide |
| **IMPLEMENTATION_SUMMARY.md** | Implementation details |

---

## 🐛 Troubleshooting

### Common Issues

**"Module not found: langchain_groq"**
```bash
source venv/bin/activate
pip install -r requirements.txt
```

**"GROQ_API_KEY not set"**
```bash
# Create .env file
cp .env.example .env
# Add your API key to .env
```

**"No such table: assessments_assessmentsession"**
```bash
python manage.py migrate
```

**Templates not found**
```bash
# Check TEMPLATES setting in config/settings.py
# Verify templates are in assessments/templates/assessments/
```

**CSRF token missing (AJAX)**
```bash
# Make sure you're using @csrf_exempt or including token
# See assessments/views.py for examples
```

---

## 📊 Performance

### Groq vs OpenAI Comparison

| Metric | Groq (Llama 3.1 70B) | OpenAI (GPT-4o-mini) |
|--------|---------------------|---------------------|
| **Latency** | 0.5-1s ⚡ | 2-4s |
| **Speed** | 3-4x faster | Baseline |
| **Quality** | Excellent ✅ | Excellent ✅ |
| **Cost** | Competitive 💰 | Higher |
| **Model** | Open-source | Proprietary |

**Winner**: Groq for speed, comparable quality, lower cost!

---

## 🤝 Contributing

This is an educational project demonstrating:
- LangGraph state machine implementation
- LangChain tool integration
- Django + AI agent architecture
- Mental health assessment workflows
- Human-in-the-loop design patterns

---

## 📄 License

MIT License - See LICENSE file for details

---

## ⚠️ Disclaimer

**This system is for professional use only.** It does not diagnose, treat, or provide medical advice. Always consult qualified mental health professionals for diagnosis and treatment.

If you or someone you know is in crisis, please contact emergency services or a crisis hotline immediately:
- **National Suicide Prevention Lifeline**: 988
- **Crisis Text Line**: Text HOME to 741741
- **Emergency Services**: 911

---

## 🚀 Get Started Now

```bash
# 1. Navigate to project
cd /Users/Projects/mental-health-assessment

# 2. Activate environment
source venv/bin/activate

# 3. Add Groq API key to .env
cp .env.example .env
# Edit .env file

# 4. Run server
python manage.py runserver

# 5. Visit http://localhost:8000
```

---

**Built with Django, LangChain, LangGraph, and Groq AI**

For detailed documentation, see [ARCHITECTURE.md](ARCHITECTURE.md)
