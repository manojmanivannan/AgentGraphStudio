"""PROTOTYPE — throwaway scenarios for issue #78 (Output-extraction mechanism).

Each scenario describes the *same* conceptual case, expressed once per
mechanism's raw material shape, so the TUI can flip mechanisms on one
scenario and compare ergonomics/edge-case handling directly.
"""

from __future__ import annotations

from prototype_output_extraction.logic import AttachmentSlot

# The mock agent's declared *output* Attachment nodes (data model per #76).
SLOTS: list[AttachmentSlot] = [
    AttachmentSlot(name="report", file_type="csv"),
    AttachmentSlot(name="chart", file_type="image"),
]

SCENARIOS: list[dict] = [
    {
        "label": "1. Happy path — single csv attachment + normal prose",
        "tagged_block_final_answer": (
            "Here is your quarterly summary.\n\n"
            '<attachment name="report" type="csv">a,b\n1,2\n3,4</attachment>\n\n'
            "Let me know if you need anything else."
        ),
        "output_field_final_answer": (
            "Here is your quarterly summary. Let me know if you need anything else."
        ),
        "output_field_attachments": [{"name": "report", "file_type": "csv", "content": "a,b\n1,2\n3,4"}],
        "tool_call_final_answer": (
            "Here is your quarterly summary. [[attachment:report]] "
            "Let me know if you need anything else."
        ),
        "tool_calls": [
            {
                "tool": "emit_attachment",
                "args": {"name": "report", "file_type": "csv", "content": "a,b\n1,2\n3,4"},
                "ref": "[[attachment:report]]",
            }
        ],
    },
    {
        "label": "2. Two attachments in one answer (csv + image)",
        "tagged_block_final_answer": (
            "Summary attached, plus the trend chart.\n\n"
            '<attachment name="report" type="csv">a,b\n1,2</attachment>\n'
            '<attachment name="chart" type="image">/api/plots/abc123</attachment>'
        ),
        "output_field_final_answer": "Summary attached, plus the trend chart.",
        "output_field_attachments": [
            {"name": "report", "file_type": "csv", "content": "a,b\n1,2"},
            {"name": "chart", "file_type": "image", "content": "/api/plots/abc123"},
        ],
        "tool_call_final_answer": (
            "Summary attached [[attachment:report]], plus the trend chart [[attachment:chart]]."
        ),
        "tool_calls": [
            {
                "tool": "emit_attachment",
                "args": {"name": "report", "file_type": "csv", "content": "a,b\n1,2"},
                "ref": "[[attachment:report]]",
            },
            {
                "tool": "emit_attachment",
                "args": {"name": "chart", "file_type": "image", "content": "/api/plots/abc123"},
                "ref": "[[attachment:chart]]",
            },
        ],
    },
    {
        "label": "3. Malformed — unclosed tag / missing field / dropped reference",
        "tagged_block_final_answer": (
            'Here you go.\n\n<attachment name="report" type="csv">a,b\n1,2'
            # no closing tag
        ),
        "output_field_final_answer": "Here you go.",
        "output_field_attachments": [{"name": "report", "content": "a,b\n1,2"}],  # missing file_type
        "tool_call_final_answer": "Here you go.",  # agent forgot to include the [[attachment:report]] ref
        "tool_calls": [
            {
                "tool": "emit_attachment",
                "args": {"name": "report", "file_type": "csv", "content": "a,b\n1,2"},
                "ref": "[[attachment:report]]",
            }
        ],
    },
    {
        "label": "4. Type mismatch — agent's declared type disagrees with the canvas",
        "tagged_block_final_answer": (
            "Text summary attached.\n\n"
            '<attachment name="report" type="text">just prose, not csv</attachment>'
        ),
        "output_field_final_answer": "Text summary attached.",
        "output_field_attachments": [{"name": "report", "file_type": "text", "content": "just prose, not csv"}],
        "tool_call_final_answer": "Text summary attached. [[attachment:report]]",
        "tool_calls": [
            {
                "tool": "emit_attachment",
                "args": {"name": "report", "file_type": "text", "content": "just prose, not csv"},
                "ref": "[[attachment:report]]",
            }
        ],
    },
    {
        "label": "5. Unknown attachment name — not wired to any Attachment node",
        "tagged_block_final_answer": (
            'Bonus file for you.\n\n<attachment name="scratch_notes" type="text">misc notes</attachment>'
        ),
        "output_field_final_answer": "Bonus file for you.",
        "output_field_attachments": [{"name": "scratch_notes", "file_type": "text", "content": "misc notes"}],
        "tool_call_final_answer": "Bonus file for you. [[attachment:scratch_notes]]",
        "tool_calls": [
            {
                "tool": "emit_attachment",
                "args": {"name": "scratch_notes", "file_type": "text", "content": "misc notes"},
                "ref": "[[attachment:scratch_notes]]",
            }
        ],
    },
    {
        "label": "6. Generalization check — plot markdown link alongside an attachment",
        "tagged_block_final_answer": (
            "See the chart below.\n\n![Plot](/api/plots/xyz789)\n\n"
            '<attachment name="report" type="csv">a,b\n1,2</attachment>'
        ),
        "output_field_final_answer": "See the chart below.\n\n![Plot](/api/plots/xyz789)",
        "output_field_attachments": [{"name": "report", "file_type": "csv", "content": "a,b\n1,2"}],
        "tool_call_final_answer": (
            "See the chart below.\n\n![Plot](/api/plots/xyz789)\n\n[[attachment:report]]"
        ),
        "tool_calls": [
            {
                "tool": "emit_attachment",
                "args": {"name": "report", "file_type": "csv", "content": "a,b\n1,2"},
                "ref": "[[attachment:report]]",
            }
        ],
    },
]
