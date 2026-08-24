"""
Second Opinion — pathology report analysis grounded in real-time literature.

Flow:
  1. User pastes a pathology/radiology report.
  2. Gemini extracts structured findings (diagnosis, staging, biomarkers).
  3. Exa searches the live web for current clinical trials / guidelines
     matching those findings.
  4. Gemini synthesizes a "report says X, current evidence says Y" comparison.

Run:
  pip install -r requirements.txt
  cp .env.example .env   # fill in your keys
  python app.py
  open http://localhost:5000
"""

import os
import json
import requests
from flask import Flask, request, jsonify, send_from_directory
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
EXA_API_KEY = os.environ.get("EXA_API_KEY", "")

# If your hackathon AI Studio key uses a different model name, change this.
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
)
EXA_SEARCH_URL = "https://api.exa.ai/search"

app = Flask(__name__, static_folder="static", static_url_path="")


def call_gemini(prompt: str) -> str:
    """Send a prompt to Gemini and return the plain text response."""
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    resp = requests.post(GEMINI_URL, json=body, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


def extract_findings(report_text: str) -> dict:
    """Step 1: Gemini pulls structured findings out of the raw report."""
    prompt = f"""You are a clinical data extraction assistant.
Read the pathology/radiology report below and extract the key findings as
STRICT JSON only (no markdown, no commentary) with this shape:

{{
  "diagnosis": "...",
  "staging": "...",
  "biomarkers": ["...", "..."],
  "key_findings_summary": "one or two plain-language sentences"
}}

Report:
\"\"\"{report_text}\"\"\"
"""
    raw = call_gemini(prompt)
    # Gemini sometimes wraps JSON in ```json fences — strip those defensively.
    cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {"raw_response": raw, "parse_error": True}


def mock_evidence(findings: dict) -> list:
    """Placeholder evidence used when EXA_API_KEY isn't set yet, so the
    pipeline is fully demoable before the real key arrives. Swap this out
    for search_evidence() once EXA_API_KEY is in .env — no other changes
    needed, analyze() already picks the right one automatically."""
    diagnosis = findings.get("diagnosis", "this diagnosis")
    return [
        {
            "title": f"[DEMO DATA] Recent guideline update relevant to {diagnosis}",
            "url": "https://example.com/demo-source-1",
            "snippet": "This is placeholder evidence shown because EXA_API_KEY is not set. "
                       "Once you add a real Exa key, this will be replaced by live search results.",
            "publishedDate": "2026-06-01",
        },
        {
            "title": f"[DEMO DATA] Trial matching biomarkers in this report",
            "url": "https://example.com/demo-source-2",
            "snippet": "Placeholder result — real Exa search will return an actual live source here.",
            "publishedDate": "2026-05-15",
        },
    ]


def search_evidence(findings: dict) -> list:
    """Step 2: Exa searches for current literature/trials matching findings."""
    query_parts = [
        findings.get("diagnosis", ""),
        findings.get("staging", ""),
        " ".join(findings.get("biomarkers", [])),
        "clinical trial OR treatment guideline 2026",
    ]
    query = " ".join(p for p in query_parts if p).strip()

    headers = {"x-api-key": EXA_API_KEY, "Content-Type": "application/json"}
    body = {
        "query": query,
        "numResults": 5,
        "type": "neural",
        "contents": {"text": {"maxCharacters": 1000}},
    }
    resp = requests.post(EXA_SEARCH_URL, headers=headers, json=body, timeout=60)
    resp.raise_for_status()
    results = resp.json().get("results", [])
    return [
        {
            "title": r.get("title"),
            "url": r.get("url"),
            "snippet": (r.get("text") or "")[:400],
            "publishedDate": r.get("publishedDate"),
        }
        for r in results
    ]


def synthesize(findings: dict, evidence: list) -> dict:
    """Step 3: Gemini compares report findings against retrieved evidence.
    Returns structured JSON so the UI can render matches/flags as distinct,
    scannable lists instead of a wall of text."""
    evidence_text = "\n\n".join(
        f"- {e['title']} ({e.get('publishedDate', 'n.d.')}): {e['snippet']} [{e['url']}]"
        for e in evidence
    ) or "No evidence retrieved."

    prompt = f"""You are helping a clinician sanity-check a pathology report
against current published evidence. Do NOT give medical advice or a
diagnosis — only compare and summarize what the literature says relative to
the report, and flag anything that looks outdated, missing, or worth a
second look.

REPORT FINDINGS:
{json.dumps(findings, indent=2)}

CURRENT EVIDENCE (from live web search):
{evidence_text}

Respond as STRICT JSON only (no markdown, no commentary) with this shape:

{{
  "matches": ["short bullet point", "short bullet point"],
  "flags": ["short bullet point citing a source by title", "..."],
  "confidence": "high" | "medium" | "low",
  "confidence_reason": "one short sentence explaining the confidence level"
}}

"confidence" reflects how well the retrieved evidence actually covers this
report's specific findings — low if evidence is thin, generic, or
tangential.
"""
    raw = call_gemini(prompt)
    cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {
            "matches": [],
            "flags": [],
            "confidence": "low",
            "confidence_reason": "Could not parse model output.",
            "raw_response": raw,
        }


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/api/analyze", methods=["POST"])
def analyze():
    if not GEMINI_API_KEY:
        return jsonify({"error": "Missing GEMINI_API_KEY in .env"}), 500

    report_text = (request.json or {}).get("report_text", "").strip()
    if not report_text:
        return jsonify({"error": "report_text is required"}), 400
    if len(report_text) > 8000:
        return jsonify({"error": "Report text is too long (max ~8000 characters)."}), 400

    using_demo_evidence = not bool(EXA_API_KEY)

    try:
        findings = extract_findings(report_text)
        evidence = mock_evidence(findings) if using_demo_evidence else search_evidence(findings)
        synthesis = synthesize(findings, evidence)
        return jsonify({
            "findings": findings,
            "evidence": evidence,
            "synthesis": synthesis,
            "demo_mode": using_demo_evidence,
        })
    except requests.HTTPError as e:
        return jsonify({"error": f"API call failed: {e.response.text}"}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "true").lower() == "true"
    app.run(debug=debug, host="0.0.0.0", port=port)
