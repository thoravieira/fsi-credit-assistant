"""SDD 07 acceptance — checkpointer/store construction and a store roundtrip
against real Atlas (SDD 14 §2: real DB, fake LLM — no LLM involved here)."""

from langgraph.checkpoint.mongodb import MongoDBSaver
from langgraph.store.mongodb import MongoDBStore

from app.memory.checkpointer import get_checkpointer
from app.memory.store import customer_facts_namespace, get_store


def test_checkpointer_is_mongodb_saver():
    checkpointer = get_checkpointer()
    assert isinstance(checkpointer, MongoDBSaver)


def test_store_is_mongodb_store_with_explicit_db_name():
    store = get_store()
    assert isinstance(store, MongoDBStore)


def test_store_put_get_roundtrip():
    store = get_store()
    namespace = customer_facts_namespace("TEST-ROUNDTRIP")

    store.put(namespace, key="smoke-test", value={"content": "roundtrip de teste"})
    item = store.get(namespace, "smoke-test")

    assert item is not None
    assert item.value["content"] == "roundtrip de teste"


def test_no_async_mongodb_saver_anywhere():
    import ast
    from pathlib import Path

    app_dir = Path(__file__).resolve().parents[1] / "app"
    for path in app_dir.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "AsyncMongoDBSaver" not in [a.name for a in node.names], path
                assert "mongodb.aio" not in node.module, path
