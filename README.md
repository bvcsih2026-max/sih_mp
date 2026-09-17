# MPLADS Guardian

MPLADS Guardian is an evidence-first MVP for reviewing unusual public-works implementation patterns. It produces investigation signals, not findings of fraud or legal conclusions.

## Quick start

Backend:

```powershell
cd backend
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
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

## Render and Vercel deployment

Deploy the repository root to Render using `render.yaml`. The backend service uses `backend` as its root directory, seeds the MP master/reference data on startup, stores SQLite on a persistent disk, and exposes `/api/health`.

In Vercel, import the repository with `frontend` as the project root. Set this environment variable for Production, Preview, and Development:

```text
VITE_API_BASE_URL=https://YOUR-RENDER-SERVICE.onrender.com/api
```

After the Vercel URL is known, set the Render environment variable `FRONTEND_URLS` to the Vercel URL. Multiple origins may be comma-separated. Never use `127.0.0.1` as the production API URL.

The seed data is explicitly synthetic and is labelled `SYNTHETIC / DEMO DATA - NOT OFFICIAL MPLADS DATA`. The MP master/reference JSON is supplied reference data, separate from synthetic project transactions.

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
