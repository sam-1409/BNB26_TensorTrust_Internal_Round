"""Unit tests for Phase 3: reasoning/evidence_graph.py."""

from models.schemas import Case, Artifact, Relation, EvidenceRef
from reasoning.evidence_graph import (
    build_evidence_graph,
    get_supporting_evidence,
    get_contradicting_evidence,
    get_shared_entities,
)


def test_build_evidence_graph():
    art1 = Artifact(
        id="art-1",
        modality="image",
        display_name="photo.png",
        sha256="sha1",
        status="ok",
        semantic_claims=[
            {
                "claim_text": "Meeting in Paris",
                "category": "event",
                "grounding_ref": {"type": "region", "value": "metadata"}
            }
        ],
        metadata={"entities": {"locations": ["Paris"], "dates": ["2024"]}},
    )

    art2 = Artifact(
        id="art-2",
        modality="text",
        display_name="notes.txt",
        sha256="sha2",
        status="ok",
        semantic_claims=[
            {
                "claim_text": "Meeting in London",
                "category": "event",
                "grounding_ref": {"type": "page", "value": "1"}
            }
        ],
        metadata={"entities": {"locations": ["London"], "dates": ["2024"]}},
    )

    rel_contradicts = Relation(
        source_id="art-1",
        target_id="art-2",
        relation="CONTRADICTS",
        conflict_type="location",
        method="deterministic",
        confidence_level="high",
        evidence_refs=[
            EvidenceRef(type="region", value="metadata"),
            EvidenceRef(type="page", value="1"),
        ],
        explanation="Paris vs London location conflict",
    )

    case = Case(
        id="test-case-1",
        job_status="completed",
        artifacts=[art1, art2],
        relations=[rel_contradicts],
    )

    graph = build_evidence_graph(case)

    # Check node types
    node_types = {n.node_type for n in graph.nodes}
    assert "artifact" in node_types
    assert "claim" in node_types
    assert "entity" in node_types

    # Check contradiction list
    assert len(graph.contradiction_list) == 1
    assert graph.contradiction_list[0]["artifact_a"] == "art-1"
    assert graph.contradiction_list[0]["artifact_b"] == "art-2"
    assert graph.contradiction_list[0]["conflict_type"] == "location"

    # Check graph queries
    contras = get_contradicting_evidence(graph, "art:art-1")
    assert len(contras) == 1

    shared_ents = get_shared_entities(graph)
    # Both mention 2024
    assert "ent:dates:2024" in shared_ents
    assert set(shared_ents["ent:dates:2024"]) == {"art-1", "art-2"}
