# ClaimGuard Web MVP

ClaimGuard is a fresh, local-first reimbursement demo. It uses an HTML/CSS/JavaScript website, a Flask/Python backend, and a persistent SQLite database. It is a fictional-company template: sample policies and demo data are not real company rules, and no payment integration exists.

## Start on Windows

1. Install Python 3.10 or newer if it is not installed.
2. Double-click **Start ClaimGuard.cmd**. On the first launch it creates a private `.venv` folder and installs the web/PDF packages. It waits for the local server to respond before opening the website. A separate server window opens; keep it open while using the site, and close it to stop ClaimGuard.
3. The browser opens at `http://127.0.0.1:5000`.
4. Sign in with one of the fresh demo accounts below.

The first launch needs an internet connection for Python packages. Once installed, the website and its feature-hash policy search work offline. All app files and data stay in this project folder.

### Demo accounts

| Role | Username | Password |
| --- | --- | --- |
| Employee | `asha` | `ClaimGuard123!` |
| Authority | `morgan` | `Authority123!` |

These are demonstration credentials, not production credentials. Change them before sharing the project. Passwords are stored as salted hashes in SQLite.

## Local AI setup

The chat works without a downloaded language model: policy questions are answered from retrieved handbook passages, and claim checks run through the deterministic Python policy engine. To enable the local conversational model and semantic embeddings, double-click **Set up local AI.cmd** after the first launch. This installs CPU-only runtimes, downloads a pinned Qwen 2.5 1.5B GGUF model (about 1 GB) and a small BGE sentence-embedding model, verifies the Qwen file checksum, runs a local inference, and re-indexes the policy chunks. It requires an internet connection and some disk space the first time. No ChatGPT API key or remote AI service is used.

If local AI setup is unavailable, the fallback is still functional, grounded policy retrieval. The app displays its current mode in the top bar. Local model answers are limited to retrieved policy evidence and checked before display; the model cannot approve claims, call the payment queue, or change stored records.

## What the two accounts can do

### Employee

- Ask questions about reimbursement policies. The assistant retrieves matching handbook sections from a local SQLite vector index and cites the document and page. Unrelated topics are declined.
- Start a claim conversationally by typing the expense category and date, then attaching a PDF or image receipt. If details are missing, the assistant asks for them and keeps the selected attachment in the browser for the follow-up.
- Receipt text is extracted locally from text PDFs or, when Tesseract OCR is installed, images. Image OCR is best-effort. Unreadable/missing amounts or dates and date mismatches go to authority review; they are never described as verified.
- Each uploaded receipt file is stored under `instance/uploads`, with its SHA-256 fingerprint, OCR text and status in SQLite. Re-uploading the exact same bytes is automatically rejected, even if some claim fields were omitted. Similar merchant/date/amount claims with a different file are sent for review.
- Review claim history and decisions.

### Authority

- Review uncertain receipts, unknown categories, late submissions, possible duplicates and costs above auto-approval limits. Approve or reject with a reason.
- View both auto-approved claims and authority-approved claims in a payment queue. **Confirm demo payment** records an authority action only. It does not initiate, schedule or transfer money.
- Inspect uploaded receipt files, see the local policy index count and view the SQLite audit trail.

## Fictional policy rules

All amounts are INR and are intentionally invented for an MVP.

| Category | Auto-approval cap |
| --- | ---: |
| Travel/local transport | INR 5,000 per claim |
| Meals | INR 1,500 per person/meal |
| Lodging | INR 5,000 per night |

The cap is inclusive. Higher amounts are pending review. Unknown categories, uncertain OCR, date mismatch, possible duplicates and claims more than 30 days after the expense are pending review. Future-dated expenses and exact file duplicates are rejected. Prompt-injection or policy-bypass attempts in a claim message are rejected and logged. The rules in `claim_engine.py` and the handbook in `policies/` use the same caps and outcomes.

## The sample policy library and RAG

The generated handbook contains 24 pages across four documents:

- `Travel Expense Policy.pdf` — 8 pages
- `Meals and Accommodation.pdf` — 6 pages
- `Reimbursement Approval Rules.pdf` — 5 pages
- `Expense Exceptions and FAQ.pdf` — 5 pages

That is 24 pages total. The source Markdown files sit beside the PDFs. They are fictional, labelled sample policies. Each page is a chunk, embedded locally (BGE when set up; deterministic feature-hash fallback otherwise), and stored in the SQLite `policy_vectors` table for cosine-similarity retrieval. The fallback is a lightweight lexical vector; semantic BGE is the recommended local setup.

## Data files

- SQLite database: `instance/claimguard.sqlite3`
- Uploaded receipt files: `instance/uploads/`
- Policy PDFs and Markdown source: `policies/`
- Downloaded local models: `models/`

Tables include `users`, `receipts`, `claims`, `audit_log`, and `policy_vectors`. Every completed claim decision has a claim and audit entry. Receipt fingerprints are unique. The session signing key is randomly generated and stored beside the SQLite file. The demo uses local session cookies; it is not hardened for production deployment.

## Receipt OCR note

Text-based PDFs can be read using the included `pypdf` package. For image OCR, install Tesseract OCR for Windows and ensure `tesseract.exe` is on PATH. Without the Tesseract program, image uploads are still accepted and stored, but uncertain claims go to review. A scan is not guaranteed to be readable, and OCR is not fraud or authenticity detection.

## Run the tests

In a terminal opened in this folder, run:

```powershell
python -m unittest discover -s tests -v
```

The test suite uses a temporary SQLite database and mocked receipt OCR so it never touches the demo database or requires real receipt files.

## Project map

- `app.py` — web routes, authentication, chat orchestration, and authority actions
- `claim_engine.py` — receipt fingerprinting, extraction, guardrails, and deterministic decisions
- `rag.py` — local embeddings, SQLite vector search, and sample PDF generation
- `policy_content.py` — the 24-page fictional handbook source
- `db.py` — SQLite schema and fresh demo users
- `local_ai.py` — optional local Qwen answer generation and output checks
- `templates/`, `static/` — responsive web UI
- `tests/` — backend/API and policy regression tests
