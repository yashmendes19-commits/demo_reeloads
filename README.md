# Reels Editor Marketplace

A Python (Flask) web app to hire reel editors: clients browse an editor's
reference reels, hire them directly, send custom editing instructions, and
pay for the job. Editors build a portfolio, take on jobs, and deliver the
edited reel.

## Features

- Two account roles: **client** (hires) and **editor** (offers services).
- Editors build a portfolio of **reference reels** (title, video link, style
  notes) that clients can browse before hiring.
- Clients can **hire an editor directly** after viewing their reference
  reels, skipping the open-bidding step.
- Clients give **custom editing instructions** (pacing, music, captions,
  transitions, hook, CTA, aspect ratio, etc.) for every job.
- Clients can also post an **open job** for any editor to apply/bid on, as
  an alternative to direct hire.
- Job lifecycle: `open -> assigned -> paid -> delivered -> completed`.
- A **payment step** (mock/escrow by default) with a clearly marked spot to
  plug in real Stripe Checkout.
- Editor earnings are tracked automatically once a job is marked complete.
- Security basics: hashed passwords (Werkzeug), session-based CSRF tokens
  on every form, role checks on every state-changing route.

## Stack

- **Backend:** Python, Flask, Flask-SQLAlchemy, Flask-Login, SQLite
- **Frontend:** server-rendered HTML (no separate frontend build needed)

## Getting started

### Option A: venv + pip

```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

### Option B: Conda

```bash
conda env create -f environment.yml
conda activate reels-marketplace
python app.py
```

Then open `http://127.0.0.1:5000`.

A SQLite file `reels_marketplace.db` is created automatically on first run.

## Try the flow

1. Register account #1 as **editor** -> "My Portfolio" -> add 1-2 reference
   reels.
2. Register account #2 as **client** -> "Browse Editors" -> click the
   editor -> "Hire directly" -> fill in your idea/instructions -> pay.
3. Log back into the editor account -> open the job -> submit a delivery
   link.
4. Log back into the client account -> approve/complete the job.

## Real payments

The `pay_job` view in `app.py` uses a mock/escrow flow so the app runs
standalone with no external accounts needed. It has a comment block showing
exactly where to plug in a real Stripe Checkout Session for actual card
payments.
