import uuid

from canvas_server.attachment_matching import (
    DeclaredInputNode,
    MatchOutcome,
    guess_file_type,
    match_uploads_to_nodes,
)


def test_guess_file_type_maps_known_extensions_case_insensitively():
    cases = {
        "data.csv": "csv",
        "DATA.CSV": "csv",
        "payload.json": "json",
        "notes.txt": "text",
        "README.md": "text",
        "tool.py": "python",
        "config.yaml": "yaml",
        "CONFIG.YML": "yaml",
        "image.png": "image",
        "photo.JPG": "image",
        "scan.Pdf": "pdf",
        "archive.zip": "binary",
        "no-extension": "binary",
        ".env": "binary",
    }

    for filename, expected in cases.items():
        assert guess_file_type(filename) == expected


def test_match_uploads_to_nodes_matches_unambiguous_file():
    node_id = uuid.uuid4()

    outcomes = match_uploads_to_nodes(
        ["data.csv"],
        [DeclaredInputNode(id=node_id, file_type="csv")],
    )

    assert outcomes == [
        MatchOutcome(
            filename="data.csv",
            file_type="csv",
            node_id=node_id,
            error=None,
        )
    ]


def test_match_uploads_to_nodes_rejects_when_no_declared_node_accepts_type():
    outcomes = match_uploads_to_nodes(
        ["data.csv"],
        [DeclaredInputNode(id=uuid.uuid4(), file_type="json")],
    )

    assert outcomes == [
        MatchOutcome(
            filename="data.csv",
            file_type="csv",
            node_id=None,
            error="No input attachment node on this agent accepts file type 'csv'",
        )
    ]


def test_match_uploads_to_nodes_rejects_ambiguous_type_for_every_file():
    outcomes = match_uploads_to_nodes(
        ["first.csv", "second.csv"],
        [
            DeclaredInputNode(id=uuid.uuid4(), file_type="csv"),
            DeclaredInputNode(id=uuid.uuid4(), file_type="csv"),
        ],
    )

    assert outcomes == [
        MatchOutcome(
            filename="first.csv",
            file_type="csv",
            node_id=None,
            error="Ambiguous: multiple input attachment nodes accept file type 'csv'",
        ),
        MatchOutcome(
            filename="second.csv",
            file_type="csv",
            node_id=None,
            error="Ambiguous: multiple input attachment nodes accept file type 'csv'",
        ),
    ]


def test_match_uploads_to_nodes_rejects_second_file_when_only_one_node_exists():
    node_id = uuid.uuid4()

    outcomes = match_uploads_to_nodes(
        ["first.csv", "second.csv"],
        [DeclaredInputNode(id=node_id, file_type="csv")],
    )

    assert outcomes == [
        MatchOutcome(
            filename="first.csv",
            file_type="csv",
            node_id=node_id,
            error=None,
        ),
        MatchOutcome(
            filename="second.csv",
            file_type="csv",
            node_id=None,
            error="No input attachment node on this agent accepts file type 'csv'",
        ),
    ]


def test_match_uploads_to_nodes_returns_independent_mixed_batch_results():
    csv_node_id = uuid.uuid4()
    pdf_node_id = uuid.uuid4()

    outcomes = match_uploads_to_nodes(
        ["first.csv", "notes.txt", "guide.pdf"],
        [
            DeclaredInputNode(id=csv_node_id, file_type="csv"),
            DeclaredInputNode(id=pdf_node_id, file_type="pdf"),
        ],
    )

    assert outcomes == [
        MatchOutcome(
            filename="first.csv",
            file_type="csv",
            node_id=csv_node_id,
            error=None,
        ),
        MatchOutcome(
            filename="notes.txt",
            file_type="text",
            node_id=None,
            error="No input attachment node on this agent accepts file type 'text'",
        ),
        MatchOutcome(
            filename="guide.pdf",
            file_type="pdf",
            node_id=pdf_node_id,
            error=None,
        ),
    ]
