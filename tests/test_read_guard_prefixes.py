"""Prefixed MCP read tools (Composio, Teams) pass the read-only guard; every write-like name stays blocked.

Also covers summary cleanup keeping underscores inside words. Light file: starts no Hermes hosts.
"""
from __future__ import annotations

import pytest

from alchemy_task.core import taskfile as tf
from alchemy_task.core.discovery_identity import UserError
from alchemy_task.core.reader_policy import check_binding
from alchemy_task.core.research_guard import is_write_like

ALLOWED = [
    # App prefix that differs from the server name (one Composio server for every app).
    "mcp__composio__GMAIL_FETCH_EMAILS",
    "mcp__composio__GMAIL_FETCH_MESSAGE_BY_THREAD_ID",
    "mcp__composio__GMAIL_LIST_THREADS",
    "mcp__composio__GMAIL_LIST_LABELS",
    "mcp__composio__SLACK_SEARCH_MESSAGES",
    "mcp__composio__SLACK_FETCH_CONVERSATION_HISTORY",
    "mcp__composio__MICROSOFT_TEAMS_CHATS_GET_ALL_MESSAGES",
    # Multi-word prefix on a server named after the app.
    "mcp__teams__MICROSOFT_TEAMS_CHATS_GET_ALL_MESSAGES",
    "mcp__teams__MICROSOFT_TEAMS_LIST_CHANNELS",
    # Composio lookups (search and schemas only; nothing runs).
    "mcp__composio__COMPOSIO_SEARCH_TOOLS",
    "mcp__composio__COMPOSIO_GET_TOOL_SCHEMAS",
    "mcp__connect__COMPOSIO_SEARCH_TOOLS",
    # Hosted connector with a prefix.
    "connectors__workmail__OUTLOOK_LIST_MESSAGES",
    # Existing behaviour that must not change.
    "mcp__discovery_readers__gmail_search",
    "mcp__discovery_readers__slack_search",
    "mcp__workiq__fetch",
    "connectors__gmail__GMAIL_FETCH_EMAILS",
    "mcp__linear__getIssues",
    "mcp__notion__notion-search",
]

BLOCKED = [
    "mcp__composio__GMAIL_SEND_EMAIL",
    "mcp__composio__GMAIL_CREATE_EMAIL_DRAFT",
    "mcp__composio__GMAIL_MOVE_TO_TRASH",
    "mcp__composio__GMAIL_ADD_LABEL_TO_EMAIL",
    "mcp__composio__GMAIL_MODIFY_THREAD_LABELS",
    "mcp__composio__GMAIL_REPLY_TO_THREAD",
    "mcp__composio__GMAIL_FETCH_AND_MARK_READ",
    "mcp__composio__SLACK_SENDS_A_MESSAGE_TO_A_SLACK_CHANNEL",
    "mcp__composio__SLACK_SCHEDULE_MESSAGE",
    "mcp__composio__SLACK_LIST_AND_DELETE_FILES",
    "mcp__composio__MICROSOFT_TEAMS_TEAMS_POST_CHANNEL_MESSAGE",
    "mcp__composio__MICROSOFT_TEAMS_CHATS_GET_AND_REPLY",
    # Composio meta tools that run, proxy or manage things.
    "mcp__composio__COMPOSIO_MULTI_EXECUTE_TOOL",
    "mcp__composio__COMPOSIO_REMOTE_WORKBENCH",
    "mcp__composio__COMPOSIO_REMOTE_BASH_TOOL",
    "mcp__composio__COMPOSIO_MANAGE_CONNECTIONS",
    "mcp__composio__COMPOSIO_WAIT_FOR_CONNECTIONS",
    "mcp__composio__COMPOSIO_PROXY_EXECUTE",
    "mcp__composio__COMPOSIO_GET_AND_EXECUTE",
    # Work IQ writes.
    "mcp__workiq__do_action",
    "mcp__workiq__create_entity",
    "mcp__workiq__update_entity",
    # Verbless names stay blocked (no read verb anywhere).
    "mcp__discovery_readers__gmail_thread",
    "mcp__x__inbox",
    # Earlier rules still hold.
    "mcp__x__export_and_delete",
    "mcp__x__delete_search",
    "connectors__gmail__GMAIL_SEND_EMAIL",
]


@pytest.mark.parametrize("tool", ALLOWED)
def test_prefixed_read_tools_pass(tool):
    assert is_write_like(tool) is False


@pytest.mark.parametrize("tool", BLOCKED)
def test_write_like_tools_stay_blocked(tool):
    assert is_write_like(tool) is True


def test_reader_binding_accepts_prefixed_read_tool_and_refuses_send():
    assert check_binding("mcp__composio__GMAIL_FETCH_EMAILS", ["mcp-composio"]) == ["mcp-composio"]
    with pytest.raises(UserError):
        check_binding("mcp__composio__GMAIL_SEND_EMAIL", ["mcp-composio"])
    with pytest.raises(UserError):
        check_binding("mcp__composio__MICROSOFT_TEAMS_CHATS_GET_ALL_MESSAGES", ["terminal"])


@pytest.mark.parametrize("raw,expected", [
    ("Reads GMAIL_FETCH_EMAILS and is_write_like.", "Reads GMAIL_FETCH_EMAILS and is_write_like."),
    ("Rename snake_case_name now.", "Rename snake_case_name now."),
    ("**Bold** and *italic* and `code`.", "Bold and italic and code."),
    ("_Italic_ and __bold__ words.", "Italic and bold words."),
    ("Uses `GMAIL_FETCH_EMAILS` daily.", "Uses GMAIL_FETCH_EMAILS daily."),
])
def test_summary_keeps_underscores_inside_words(raw, expected):
    assert tf.clean_summary(raw) == expected
