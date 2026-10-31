# Stock Intelligence
Personal Indian equity screening starter.

## Run backend (PowerShell)
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload

API docs: http://127.0.0.1:8000/docs

## Run frontend (second terminal)
cd frontend
npm install
npm run dev

Open the Vite URL, usually http://localhost:5173.
The starter uses illustrative demo rows, NOT live market data.
