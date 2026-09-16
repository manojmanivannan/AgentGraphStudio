import uuid

from canvas_server.output_extraction import (
    SANDBOX_REF_PREFIX,
    DeclaredOutputNode,
    ExtractedAttachment,
    ExtractionOutcome,
    declared_output_nodes,
    extract_output_attachments,
    file_type_to_format,
)


def _edge(source_node_id, target_node_id, edge_type):
    from types import SimpleNamespace

    return SimpleNamespace(
        source_node_id=source_node_id,
        target_node_id=target_node_id,
        edge_type=edge_type,
    )


def _attachment_node(node_id, name, file_type):
    from types import SimpleNamespace

    return SimpleNamespace(id=node_id, name=name, file_type=file_type)


class TestDeclaredOutputNodes:
    def test_returns_attachment_nodes_wired_via_produces_edge_from_agent(self):
        agent_id = uuid.uuid4()
        attachment_id = uuid.uuid4()
        edges = [_edge(agent_id, attachment_id, "produces")]
        attachment_nodes = [_attachment_node(attachment_id, "chart_data", "csv")]

        result = declared_output_nodes(edges, attachment_nodes, agent_id)

        assert result == [
            DeclaredOutputNode(id=attachment_id, name="chart_data", file_type="csv")
        ]

    def test_ignores_consumes_edges(self):
        agent_id = uuid.uuid4()
        attachment_id = uuid.uuid4()
        edges = [_edge(attachment_id, agent_id, "consumes")]
        attachment_nodes = [_attachment_node(attachment_id, "input_data", "csv")]

        result = declared_output_nodes(edges, attachment_nodes, agent_id)

        assert result == []

    def test_ignores_produces_edges_from_other_agents(self):
        agent_id = uuid.uuid4()
        other_agent_id = uuid.uuid4()
        attachment_id = uuid.uuid4()
        edges = [_edge(other_agent_id, attachment_id, "produces")]
        attachment_nodes = [_attachment_node(attachment_id, "chart_data", "csv")]

        result = declared_output_nodes(edges, attachment_nodes, agent_id)

        assert result == []

    def test_ignores_edges_pointing_at_unknown_node(self):
        agent_id = uuid.uuid4()
        edges = [_edge(agent_id, uuid.uuid4(), "produces")]

        result = declared_output_nodes(edges, [], agent_id)

        assert result == []

    def test_returns_multiple_declared_slots(self):
        agent_id = uuid.uuid4()
        csv_id, json_id = uuid.uuid4(), uuid.uuid4()
        edges = [
            _edge(agent_id, csv_id, "produces"),
            _edge(agent_id, json_id, "produces"),
        ]
        attachment_nodes = [
            _attachment_node(csv_id, "table", "csv"),
            _attachment_node(json_id, "summary", "json"),
        ]

        result = declared_output_nodes(edges, attachment_nodes, agent_id)

        assert result == [
            DeclaredOutputNode(id=csv_id, name="table", file_type="csv"),
            DeclaredOutputNode(id=json_id, name="summary", file_type="json"),
        ]


class TestExtractOutputAttachments:
    def test_extracts_matching_attachment(self):
        node_id = uuid.uuid4()
        slots = [DeclaredOutputNode(id=node_id, name="report", file_type="text")]

        outcome = extract_output_attachments(
            [{"name": "report", "file_type": "text", "content": "hello world"}], slots
        )

        assert outcome == ExtractionOutcome(
            attachments=[
                ExtractedAttachment(
                    node_id=node_id, name="report", file_type="text", content="hello world"
                )
            ],
            errors=[],
        )

    def test_returns_empty_outcome_for_empty_or_none_input(self):
        slots = [DeclaredOutputNode(id=uuid.uuid4(), name="report", file_type="text")]

        assert extract_output_attachments(None, slots) == ExtractionOutcome([], [])
        assert extract_output_attachments([], slots) == ExtractionOutcome([], [])

    def test_rejects_name_not_matching_any_declared_slot(self):
        slots = [DeclaredOutputNode(id=uuid.uuid4(), name="report", file_type="text")]

        outcome = extract_output_attachments(
            [{"name": "unknown", "file_type": "text", "content": "x"}], slots
        )

        assert outcome.attachments == []
        assert len(outcome.errors) == 1
        assert "unknown" in outcome.errors[0]
        assert "does not match any declared" in outcome.errors[0]

    def test_rejects_file_type_mismatch_against_declared_slot(self):
        node_id = uuid.uuid4()
        slots = [DeclaredOutputNode(id=node_id, name="report", file_type="csv")]

        outcome = extract_output_attachments(
            [{"name": "report", "file_type": "json", "content": "{}"}], slots
        )

        assert outcome.attachments == []
        assert len(outcome.errors) == 1
        assert "'csv'" in outcome.errors[0]
        assert "'json'" in outcome.errors[0]

    def test_rejects_invalid_json_content_for_json_slot(self):
        node_id = uuid.uuid4()
        slots = [DeclaredOutputNode(id=node_id, name="report", file_type="json")]

        outcome = extract_output_attachments(
            [{"name": "report", "file_type": "json", "content": "{not valid json"}], slots
        )

        assert outcome.attachments == []
        assert len(outcome.errors) == 1
        assert "not valid JSON" in outcome.errors[0]

    def test_accepts_valid_json_content_for_json_slot(self):
        node_id = uuid.uuid4()
        slots = [DeclaredOutputNode(id=node_id, name="report", file_type="json")]

        outcome = extract_output_attachments(
            [{"name": "report", "file_type": "json", "content": '{"a": 1}'}], slots
        )

        assert outcome.errors == []
        assert len(outcome.attachments) == 1

    def test_rejects_empty_content_as_soft_sanity_check_failure(self):
        node_id = uuid.uuid4()
        slots = [DeclaredOutputNode(id=node_id, name="report", file_type="text")]

        outcome = extract_output_attachments(
            [{"name": "report", "file_type": "text", "content": "   "}], slots
        )

        assert outcome.attachments == []
        assert len(outcome.errors) == 1
        assert "empty" in outcome.errors[0]

    def test_accepts_sandbox_reference_and_sets_relative_sandbox_path(self):
        node_id = uuid.uuid4()
        slots = [DeclaredOutputNode(id=node_id, name="report", file_type="pdf")]

        outcome = extract_output_attachments(
            [
                {
                    "name": "report",
                    "file_type": "pdf",
                    "content": f"{SANDBOX_REF_PREFIX}exports/final-report.pdf",
                }
            ],
            slots,
        )

        assert outcome == ExtractionOutcome(
            attachments=[
                ExtractedAttachment(
                    node_id=node_id,
                    name="report",
                    file_type="pdf",
                    content="sandbox://exports/final-report.pdf",
                    sandbox_path="exports/final-report.pdf",
                )
            ],
            errors=[],
        )

    def test_accepts_sandbox_reference_and_keeps_absolute_sandbox_path(self):
        node_id = uuid.uuid4()
        slots = [DeclaredOutputNode(id=node_id, name="report", file_type="pdf")]

        outcome = extract_output_attachments(
            [
                {
                    "name": "report",
                    "file_type": "pdf",
                    "content": f"{SANDBOX_REF_PREFIX}/sandbox/final-report.pdf",
                }
            ],
            slots,
        )

        assert outcome.attachments[0].sandbox_path == "/sandbox/final-report.pdf"
        assert outcome.errors == []

    def test_rejects_empty_sandbox_reference(self):
        node_id = uuid.uuid4()
        slots = [DeclaredOutputNode(id=node_id, name="report", file_type="pdf")]

        outcome = extract_output_attachments(
            [{"name": "report", "file_type": "pdf", "content": SANDBOX_REF_PREFIX}],
            slots,
        )

        assert outcome.attachments == []
        assert len(outcome.errors) == 1
        assert "sandbox://" in outcome.errors[0]
        assert "empty" in outcome.errors[0]

    def test_sandbox_reference_still_enforces_declared_slot_matching(self):
        slots = [DeclaredOutputNode(id=uuid.uuid4(), name="report", file_type="pdf")]

        outcome = extract_output_attachments(
            [
                {
                    "name": "report",
                    "file_type": "text",
                    "content": f"{SANDBOX_REF_PREFIX}exports/final-report.txt",
                }
            ],
            slots,
        )

        assert outcome.attachments == []
        assert len(outcome.errors) == 1
        assert "'pdf'" in outcome.errors[0]
        assert "'text'" in outcome.errors[0]

    def test_literal_content_entries_remain_unchanged_and_have_no_sandbox_path(self):
        node_id = uuid.uuid4()
        slots = [DeclaredOutputNode(id=node_id, name="report", file_type="text")]

        outcome = extract_output_attachments(
            [{"name": "report", "file_type": "text", "content": "hello world"}], slots
        )

        assert outcome.attachments[0].content == "hello world"
        assert outcome.attachments[0].sandbox_path is None

    def test_rejects_malformed_entry_missing_required_keys(self):
        slots = [DeclaredOutputNode(id=uuid.uuid4(), name="report", file_type="text")]

        outcome = extract_output_attachments([{"name": "report"}], slots)

        assert outcome.attachments == []
        assert len(outcome.errors) == 1

    def test_rejects_non_dict_entry(self):
        slots = [DeclaredOutputNode(id=uuid.uuid4(), name="report", file_type="text")]

        outcome = extract_output_attachments(["not-a-dict"], slots)

        assert outcome.attachments == []
        assert len(outcome.errors) == 1

    def test_errors_are_formatted_tool_output_style_and_never_raise(self):
        slots = [DeclaredOutputNode(id=uuid.uuid4(), name="report", file_type="text")]

        outcome = extract_output_attachments(
            [{"name": "unknown", "file_type": "text", "content": "x"}], slots
        )

        assert outcome.errors[0].startswith("Execution error in output_attachments")

    def test_processes_independent_mixed_batch_without_short_circuiting(self):
        good_id = uuid.uuid4()
        slots = [
            DeclaredOutputNode(id=good_id, name="good", file_type="text"),
            DeclaredOutputNode(id=uuid.uuid4(), name="other", file_type="csv"),
        ]

        outcome = extract_output_attachments(
            [
                {"name": "good", "file_type": "text", "content": "ok"},
                {"name": "nope", "file_type": "text", "content": "x"},
            ],
            slots,
        )

        assert outcome.attachments == [
            ExtractedAttachment(node_id=good_id, name="good", file_type="text", content="ok")
        ]
        assert len(outcome.errors) == 1


class TestFileTypeToFormat:
    def test_maps_known_file_types_to_storage_extensions(self):
        cases = {
            "text": "txt",
            "csv": "csv",
            "json": "json",
            "python": "py",
            "yaml": "yaml",
            "pdf": "pdf",
            "image": "png",
            "binary": "bin",
        }
        for file_type, expected in cases.items():
            assert file_type_to_format(file_type) == expected

    def test_falls_back_to_bin_for_unknown_freeform_type(self):
        assert file_type_to_format("some-custom-type") == "bin"
