# Second Opinion

A real-time, evidence-grounded sanity-check for pathology reports — built for
Moonlighting with Gemini + Exa.

Gemini extracts the key clinical findings from a pathology report. Exa
searches the live web for current clinical trials and treatment guidelines
matching those findings. Gemini then compares the two and flags anything
worth a second look.

Built on top of the extraction approach from
[Synapse Bridge](https://synapsebridge.ai), extended with live
evidence-grounding.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# open .env and paste in your GEMINI_API_KEY and EXA_API_KEY
```

**Gemini key**: from the Google AI Studio link/credentials in your hackathon
email — inside AI Studio, click "Get API key" and copy it in.

**Exa key**: from your Exa dashboard at https://dashboard.exa.ai (API Keys
tab).

## Run

```bash
python app.py
```

Then open http://localhost:5000

## Demo script (for judges)

1. Paste a sample pathology report (see `sample_report.txt`).
2. Click "Analyze report."
3. Walk through the three panels as they populate:
   - **Extracted findings** — what Gemini pulled from the raw report
   - **Current evidence** — what Exa found live on the web, with dates and
     sources
   - **Comparison** — Gemini's synthesis of what matches and what's worth a
     second look

## Notes

- This is a hackathon demo, not a medical device — it does not diagnose or
  recommend treatment. Say this out loud in the demo.
- If `GEMINI_MODEL` in `.env` throws a 404, check AI Studio for the current
  model name and update it — model names change over time.
- Keys are read server-side only (never exposed to the browser).
