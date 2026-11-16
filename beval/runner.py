"""Run every model on every bank, N times. Resume-safe: existing runs are skipped.

Usage:
  python -m beval.runner                       # baseline, all models, all banks
  python -m beval.runner --only-model openai --only-bank PNC --runs 1   # smoke test
  python -m beval.runner --condition scaffold  # adds context/<TICKER>.md to the prompt
  python -m beval.runner --provider-override mock   # offline dry run (tests)

Output: runs/<condition>/<label>/<TICKER>/run<k>.json  (raw text, parsed JSON, usage, latency)
Plain HTTPS calls (requests) to each lab's public API, so there are no SDK version differences.
"""

import argparse
import datetime as dt
import json
import os
import random
import re
import time
from pathlib import Path

import requests

from .prompt import SYSTEM, build_prompt

ROOT = Path(__file__).resolve().parent.parent
TIMEOUT = 900


# ---------------------------------------------------------------- providers
def call_openai(model, system, user, max_tokens):
    r = requests.post(
        "https://api.openai.com/v1/responses",
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
        json={"model": model, "instructions": system, "input": user,
              "max_output_tokens": max_tokens},
        timeout=TIMEOUT)
    r.raise_for_status()
    d = r.json()
    text = "".join(c.get("text", "") for item in d.get("output", []) if item.get("type") == "message"
                   for c in item.get("content", []) if c.get("type") == "output_text")
    u = d.get("usage", {})
    return text, {"input_tokens": u.get("input_tokens"), "output_tokens": u.get("output_tokens"),
                  "model_reported": d.get("model")}


def call_anthropic(model, system, user, max_tokens):
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"},
        json={"model": model, "max_tokens": max_tokens, "system": system,
              "messages": [{"role": "user", "content": user}]},
        timeout=TIMEOUT)
    r.raise_for_status()
    d = r.json()
    text = "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")
    u = d.get("usage", {})
    return text, {"input_tokens": u.get("input_tokens"), "output_tokens": u.get("output_tokens"),
                  "model_reported": d.get("model"), "stop_reason": d.get("stop_reason")}


def call_google(model, system, user, max_tokens):
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
        json={"systemInstruction": {"parts": [{"text": system}]},
              "contents": [{"role": "user", "parts": [{"text": user}]}],
              "generationConfig": {"maxOutputTokens": max_tokens}},
        timeout=TIMEOUT)
    r.raise_for_status()
    d = r.json()
    cand = (d.get("candidates") or [{}])[0]
    text = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []) if not p.get("thought"))
    u = d.get("usageMetadata", {})
    return text, {"input_tokens": u.get("promptTokenCount"), "output_tokens": u.get("candidatesTokenCount"),
                  "model_reported": d.get("modelVersion"), "finish_reason": cand.get("finishReason")}


def call_mock(model, system, user, max_tokens, *, ticker=None, seed=0):
    """Offline stand-in: answers from ground truth with deliberate, seeded errors."""
    rng = random.Random(f"{ticker}-{model}-{seed}")
    gt = json.loads((ROOT / "ground_truth" / f"{ticker}.json").read_text())
    metrics = {}
    for k, v in gt["metrics"].items():
        val, src = v["value"], v.get("source")
        if val is not None and rng.random() < 0.15:
            val = round(val * rng.choice([1.03, 0.97, 10]), 4)        # wrong number
        if src and rng.random() < 0.1:
            src = "B0001"                                           # bad citation
        metrics[k] = {"value": val, "source": src, "not_disclosed": val is None}
    prior = {k: {"value": v["value"], "source": v.get("source")} for k, v in gt["prior_quarter"].items()}
    changes = {k: round(metrics[k]["value"] - prior[k]["value"], 4)
               for k in prior if metrics[k]["value"] is not None and prior[k]["value"] is not None}
    out = {"metrics": metrics, "prior_quarter": prior, "changes_qoq": changes,
           "eps_basis_used_in_note": rng.choice(["reported", "adjusted"]),
           "nim_basis": rng.choice(["FTE", "GAAP"]), "notable_items": [], "guidance": [],
           "note_markdown": f"**{ticker}**: mock note (seed {seed})."}
    return "```json\n" + json.dumps(out) + "\n```", {"input_tokens": len(user) // 4, "output_tokens": 900,
                                                    "model_reported": model}


PROVIDERS = {"openai": call_openai, "anthropic": call_anthropic, "google": call_google, "mock": call_mock}


# ---------------------------------------------------------------- parsing
def parse_json(text: str):
    t = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if m:
        t = m.group(1)
    start, end = t.find("{"), t.rfind("}")
    if start < 0 or end < 0:
        return None, "no JSON object found"
    t = t[start:end + 1]
    try:
        return json.loads(t), None
    except json.JSONDecodeError as e:
        # models sometimes copy the // comments from the schema example
        stripped = re.sub(r'^\s*//.*$', "", t, flags=re.M)
        stripped = re.sub(r",(\s*[}\]])", r"\1", stripped)
        try:
            return json.loads(stripped), "recovered after removing comments"
        except json.JSONDecodeError:
            return None, f"invalid JSON: {e}"


# ---------------------------------------------------------------- main loop
def with_retries(fn, *a, **kw):
    for attempt in range(5):
        try:
            return fn(*a, **kw)
        except requests.HTTPError as e:
            code = e.response.status_code if e.response is not None else 0
            if code in (429, 500, 502, 503, 504, 529) and attempt < 4:
                time.sleep(20 * (attempt + 1))
                continue
            raise
        except (requests.ConnectionError, requests.Timeout):
            if attempt < 4:
                time.sleep(20 * (attempt + 1))
                continue
            raise


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--condition", default="baseline", choices=["baseline", "scaffold"])
    ap.add_argument("--only-model", nargs="*")
    ap.add_argument("--only-bank", nargs="*")
    ap.add_argument("--runs", type=int)
    ap.add_argument("--provider-override", choices=list(PROVIDERS))
    args = ap.parse_args()

    banks_cfg = json.loads((ROOT / "config" / "banks.json").read_text())
    models_cfg = json.loads((ROOT / "config" / "models.json").read_text())
    n_runs = args.runs or models_cfg["runs_per_model"]

    for m in models_cfg["models"]:
        if args.only_model and m["label"] not in args.only_model:
            continue
        provider = args.provider_override or m["provider"]
        for bank in banks_cfg["banks"]:
            t = bank["ticker"]
            if args.only_bank and t not in args.only_bank:
                continue
            doc_path = ROOT / "prepared" / t / "document.txt"
            if not doc_path.exists():
                print(f"skip {t}: run beval.fetch and beval.prepare first")
                continue
            ctx_path = ROOT / "context" / f"{t}.md"
            context = ctx_path.read_text() if args.condition == "scaffold" and ctx_path.exists() else None
            prompt = build_prompt(bank["name"], banks_cfg["quarter"], doc_path.read_text(), context)
            for k in range(1, n_runs + 1):
                out = ROOT / "runs" / args.condition / m["label"] / t / f"run{k}.json"
                if out.exists():
                    continue
                out.parent.mkdir(parents=True, exist_ok=True)
                t0 = time.time()
                kw = {"ticker": t, "seed": k} if provider == "mock" else {}
                try:
                    text, usage = with_retries(PROVIDERS[provider], m["model"], SYSTEM, prompt,
                                               models_cfg["max_output_tokens"], **kw)
                    error = None
                except Exception as e:  # keep going; record the failure as a result
                    text, usage, error = "", {}, f"{type(e).__name__}: {e}"
                parsed, parse_note = parse_json(text) if text else (None, "no output")
                rec = {"label": m["label"], "provider": provider, "model": m["model"], "ticker": t,
                       "run": k, "condition": args.condition,
                       "started_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                       "latency_s": round(time.time() - t0, 1), "usage": usage, "error": error,
                       "parse_note": parse_note, "parsed": parsed, "raw_text": text}
                out.write_text(json.dumps(rec, indent=1))
                status = "ERROR " + error if error else (parse_note or "ok")
                print(f"{args.condition}/{m['label']}/{t}/run{k}: {status} ({rec['latency_s']}s)")


if __name__ == "__main__":
    main()
