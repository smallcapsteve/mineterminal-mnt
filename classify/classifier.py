"""
Event classifier — Claude-based.

Input:  raw press release dict (headline + body)
Output: (event_type, confidence, summary, tags, model_string)
"""
from __future__ import annotations
import json
import os
import re
from pathlib import Path

import anthropic

MODEL = os.environ.get("MNT_CLASSIFIER_MODEL", "claude-sonnet-4-6")
PROMPT_PATH = Path(__file__).parent / "prompts" / "news_item.txt"

EVENT_TYPES = {
    "news_item", "drill_result", "resource_estimate", "econ_study",
    "financing", "mgmt_change", "paid_promotion", "production_update",
}

_client = None
def _get_client():
    global _client
    if _client is None:
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY env var not set")
        _client = anthropic.Anthropic(api_key=key)
    return _client


def _prompt(headline: str, body: str) -> str:
    tpl = PROMPT_PATH.read_text()
    # Trim body to ~8k chars — plenty for classification without burning tokens
    return tpl.replace("{{HEADLINE}}", headline).replace("{{BODY}}", body[:8000])


def _extract_json(text: str) -> dict | None:
    """Claude sometimes wraps JSON in ```json fences despite instructions."""
    text = text.strip()
    # strip fences
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if m:
        text = m.group(1)
    # find first {...} block
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def classify(headline: str, body: str) -> dict:
    """
    Returns:
      {
        "event_type": str,
        "classifier_confidence": float,
        "summary": str,
        "tags": [str, ...],
        "classifier_model": str
      }

    Option A mode (default): LLM call is skipped entirely. Every release
    is tagged news_item with confidence 1.0 — zero API cost. Enable the
    classifier later by setting MNT_CLASSIFIER_MODE=on in /opt/mnt/app/.env
    (and ensuring ANTHROPIC_API_KEY is set).

    Falls back to a low-confidence news_item on any API error.
    """
    mode = os.environ.get("MNT_CLASSIFIER_MODE", "off").lower()
    if mode != "on" or not os.environ.get("ANTHROPIC_API_KEY"):
        return {
            "event_type": "news_item",
            "classifier_confidence": 1.0,
            "summary": headline[:280],
            "tags": [],
            "classifier_model": "disabled",
        }

    try:
        client = _get_client()
        msg = client.messages.create(
            model=MODEL,
            max_tokens=512,
            messages=[{"role": "user", "content": _prompt(headline, body)}],
        )
        raw = "".join(
            b.text for b in msg.content if getattr(b, "type", None) == "text"
        )
        parsed = _extract_json(raw) or {}

        ev = parsed.get("event_type")
        if ev not in EVENT_TYPES:
            ev = "news_item"
        conf = parsed.get("classifier_confidence")
        try:
            conf = max(0.0, min(1.0, float(conf)))
        except Exception:
            conf = 0.3
        summary = (parsed.get("summary") or headline)[:280]
        tags    = parsed.get("tags") or []
        if not isinstance(tags, list):
            tags = []
        tags = [str(t)[:40] for t in tags[:10]]

        return {
            "event_type": ev,
            "classifier_confidence": conf,
            "summary": summary,
            "tags": tags,
            "classifier_model": MODEL,
        }
    except Exception as e:
        return {
            "event_type": "news_item",
            "classifier_confidence": 0.0,
            "summary": headline[:280],
            "tags": ["classifier_error"],
            "classifier_model": MODEL,
            "error": str(e)[:200],
        }
