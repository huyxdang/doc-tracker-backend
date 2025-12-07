# Document Change Tracker - Backend

API service for comparing Word documents and classifying change impacts.

## Architecture

```
app/
├── main.py              # FastAPI routes
├── config.py            # Settings & environment
│
├── models/
│   ├── enums.py         # ImpactLevel, ChangeType
│   └── schemas.py       # Data models & API schemas
│
├── services/
│   ├── parser.py        # Document parsing (.docx → blocks)
│   ├── differ.py        # Diff engine (block & word level)
│   ├── classifier.py    # Hybrid classification (rules + LLM)
│   └── annotator.py     # Generate highlighted documents
│
└── utils/
    └── storage.py       # Document storage (in-memory)
```

## Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Create .env file
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY

# Run server
uvicorn app.main:app --reload
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Health check |
| GET | `/health` | Deployment health check |
| POST | `/api/compare` | Compare two documents |
| GET | `/api/download/{id}` | Download annotated document |

## Classification Approach

**Hybrid Pipeline:**
1. **Rule-based** (fast, free): Detects numerical changes (percentages, currency, numbers) → CRITICAL
2. **LLM-based** (smart, costly): Analyzes semantic changes for business impact → CRITICAL/MEDIUM/LOW

**Impact Levels:**
- **CRITICAL**: Financial, legal, or contractual impact
- **MEDIUM**: Semantic changes without direct business impact
- **LOW**: Formatting, typos, synonyms

## Deployment (Railway)

1. Push to GitHub
2. Connect to Railway
3. Set environment variable: `OPENAI_API_KEY`
4. Deploy

Entry point: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
