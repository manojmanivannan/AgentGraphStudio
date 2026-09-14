"""PROTOTYPE — scenarios for issue #81 (Runtime representation & consumption
of attachment instances). See logic.py for the policies these are run against.
"""

from __future__ import annotations

from prototype_runtime_representation.logic import ConsumingAgent, InputAttachment, OutputAttachmentDraft

# --- Input-side scenarios: (label, InputAttachment, ConsumingAgent) ---------

INPUT_SCENARIOS = [
    {
        "label": "1. Small CSV input, coding-enabled agent",
        "attachment": InputAttachment(
            name="orders.csv",
            file_type="csv",
            content_text="id,total\n1,42.50\n2,17.00\n",
            size_bytes=27,
        ),
        "agent": ConsumingAgent(name="analyst", coding_enabled=True),
    },
    {
        "label": "2. Large CSV input (2MB), coding-enabled agent",
        "attachment": InputAttachment(
            name="transactions.csv",
            file_type="csv",
            content_text="id,total,ts\n" + "1,42.50,2024-01-01T00:00:00\n" * 5000,
            size_bytes=2_100_000,
        ),
        "agent": ConsumingAgent(name="analyst", coding_enabled=True),
    },
    {
        "label": "3. Image input, chat-only agent (no sandbox)",
        "attachment": InputAttachment(
            name="chart.png",
            file_type="image",
            content_text="",
            size_bytes=340_000,
        ),
        "agent": ConsumingAgent(name="summarizer", coding_enabled=False),
    },
    {
        "label": "4. Image input, coding-enabled agent",
        "attachment": InputAttachment(
            name="chart.png",
            file_type="image",
            content_text="",
            size_bytes=340_000,
        ),
        "agent": ConsumingAgent(name="analyst", coding_enabled=True),
    },
    {
        "label": "5. Binary/pdf input, chat-only agent (no sandbox)",
        "attachment": InputAttachment(
            name="report.pdf",
            file_type="pdf",
            content_text="",
            size_bytes=900_000,
        ),
        "agent": ConsumingAgent(name="summarizer", coding_enabled=False),
    },
    {
        "label": "6. Binary/pdf input, coding-enabled agent",
        "attachment": InputAttachment(
            name="report.pdf",
            file_type="pdf",
            content_text="",
            size_bytes=900_000,
        ),
        "agent": ConsumingAgent(name="analyst", coding_enabled=True),
    },
]

# --- Output-side scenario: does #78's output_attachments OutputField cover a
# sandbox-computed file without the LM re-typing it? -----------------------

OUTPUT_SCENARIOS = [
    {
        "label": "7. Small LM-authored output attachment (summary.txt)",
        "draft": OutputAttachmentDraft(
            name="summary.txt",
            file_type="text",
            content="Q1 revenue rose 12% driven by the enterprise segment.",
        ),
    },
    {
        "label": "8. 5MB sandbox-computed output attachment (result.csv)",
        "draft": OutputAttachmentDraft(
            name="result.csv",
            file_type="csv",
            content="sandbox://tmp/result.csv",
        ),
    },
]
