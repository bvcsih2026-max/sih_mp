# MPLADS Guardian

MPLADS Guardian is an evidence-first MVP for reviewing unusual public-works implementation patterns. It produces investigation signals, not findings of fraud or legal conclusions.

## Quick start

Backend:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python seed.py
python -m uvicorn app.main:app --reload
```

Frontend:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. The backend API is at `http://127.0.0.1:8000/docs`.

The seed data is explicitly synthetic and is labelled `SYNTHETIC / DEMO DATA - NOT OFFICIAL MPLADS DATA`. No MP master/reference dataset was present in the repository, so the seed does not invent official MP identities.

## Architecture

`backend/app/analysis/pipeline.py` validates records, calls the existing financial, progress, and similarity detectors, normalizes their outputs, stores signals and evidence links, and creates investigation records. SQLite stores MP, project, payment, signal, investigation, and evidence data.

The frontend consumes the REST API through `frontend/src/services/api.ts`. The main workflow is: data, validation, detection, correlation, explanation, evidence review, and human status decision.

## Tests

```powershell
cd backend
python -m pytest
```

## Limitations

The MVP has no official project dataset, authentication, asynchronous job queue, payment detector, or LLM. Guardian AI is deterministic evidence retrieval rather than a generative chatbot. Similarity analysis is capped at 500 projects per run.
# sih_mp