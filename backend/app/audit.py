"""SDD 02 §6 — the append-only audit trail.

One writer for every `decisions_log` entry, so `seq`, `model` and
`prompt_version` are populated identically on every path — including the
automatic ones. An audit trail that only covers the cases a human touched is
not an audit trail, and prompt provenance that only some events carry is not
provenance.
"""

from datetime import datetime, timezone
from typing import Any

from app.config import get_settings
from app.db import get_db
from app.graph.prompts import PROMPT_VERSION


def append_event(application_id: str, event_type: str, actor: dict, **fields: Any) -> dict:
    """Append one event and return it.

    `seq` is derived by counting, which is not concurrency-safe. Correct here
    because a thread is one application and one application is one conversation
    at a time; a production system would use an atomic counter.
    """
    db = get_db()
    entry = {
        "application_id": application_id,
        "thread_id": application_id,  # SDD 04 §1 — thread_id == application_id
        "seq": db["decisions_log"].count_documents({"application_id": application_id}) + 1,
        "event_type": event_type,
        "actor": actor,
        **fields,
        "model": get_settings().llm_model,
        "prompt_version": PROMPT_VERSION,
        "created_at": datetime.now(timezone.utc),
    }
    db["decisions_log"].insert_one(entry)
    return entry
