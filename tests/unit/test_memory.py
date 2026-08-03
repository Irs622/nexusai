"""
Unit tests for SQLiteMemory system.
"""

import pytest
from nexusai.memory.sqlite_memory import SQLiteMemory


@pytest.mark.asyncio
async def test_sqlite_memory_crud() -> None:
    memory = SQLiteMemory(db_path=":memory:")
    await memory.initialize_db()

    session_id = "test_session_1"

    # 1. Add messages
    await memory.add_message(session_id, "user", "Hello NexusAI")
    await memory.add_message(session_id, "assistant", "Hello User")
    await memory.add_message(session_id, "user", "Open Safari")
    await memory.add_message(session_id, "assistant", "Tool call: macos_open_app", name="macos_open_app")
    await memory.add_message(session_id, "tool", "Application 'Safari' activated.", name="macos_open_app")

    # 2. Get messages
    messages = await memory.get_messages(session_id, limit=50)
    assert len(messages) == 5
    assert messages[0] == {"role": "user", "content": "Hello NexusAI"}
    assert messages[1] == {"role": "assistant", "content": "Hello User"}
    assert messages[3] == {"role": "assistant", "content": "Tool call: macos_open_app", "name": "macos_open_app"}
    assert messages[4] == {"role": "tool", "content": "Application 'Safari' activated.", "name": "macos_open_app"}

    # 3. Test limit
    limited = await memory.get_messages(session_id, limit=2)
    assert len(limited) == 2
    assert limited[0]["content"] == "Tool call: macos_open_app"
    assert limited[1]["content"] == "Application 'Safari' activated."

    # 4. Clear session
    await memory.clear_session(session_id)
    cleared = await memory.get_messages(session_id)
    assert len(cleared) == 0


@pytest.mark.asyncio
async def test_sqlite_memory_multi_session_isolation() -> None:
    memory = SQLiteMemory(db_path=":memory:")
    await memory.initialize_db()

    await memory.add_message("session_a", "user", "Message A")
    await memory.add_message("session_b", "user", "Message B")

    msgs_a = await memory.get_messages("session_a")
    msgs_b = await memory.get_messages("session_b")

    assert len(msgs_a) == 1
    assert msgs_a[0]["content"] == "Message A"

    assert len(msgs_b) == 1
    assert msgs_b[0]["content"] == "Message B"

    await memory.clear_session("session_a")

    assert len(await memory.get_messages("session_a")) == 0
    assert len(await memory.get_messages("session_b")) == 1
