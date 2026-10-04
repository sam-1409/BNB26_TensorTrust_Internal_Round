"""Evidence Graph module for TrustLayers (T²).

Constructs an explicit graph connecting:
- Artifacts
- Claims
- Entities
- Platform Sources
- Evidence & Relations (SUPPORTS, CONTRADICTS, MATCHES, LINKED, UNCERTAIN)

Enforces:
- Schema-locked EvidenceGraph, EvidenceGraphNode, EvidenceGraphEdge.
- Extracts explicit contradiction records for cross-artifact discrepancies.
- Provides queries for graph traversal and support/contradiction inspection.
"""

from typing import List, Dict, Any, Optional
from models.schemas import (
    Case,
    Artifact,
    Relation,
    EvidenceGraph,
    EvidenceGraphNode,
    EvidenceGraphEdge,
    EvidenceRef,
)


def build_evidence_graph(case: Case) -> EvidenceGraph:
    """Build a unified evidence graph from a processed Case.

    Args:
        case: Processed Case instance.

    Returns:
        Populated EvidenceGraph instance.
    """
    nodes: List[EvidenceGraphNode] = []
    edges: List[EvidenceGraphEdge] = []
    contradiction_list: List[Dict[str, Any]] = []
    existing_node_ids = set()

    def add_node(node_id: str, node_type: str, label: str, art_id: Optional[str] = None):
        if node_id not in existing_node_ids:
            nodes.append(
                EvidenceGraphNode(
                    node_id=node_id,
                    node_type=node_type,
                    label=label,
                    artifact_id=art_id,
                )
            )
            existing_node_ids.add(node_id)

    # 1. Add Artifact nodes and extracted claims/entities
    for art in case.artifacts:
        art_node_id = f"art:{art.id}"
        add_node(art_node_id, "artifact", f"{art.display_name} ({art.modality})", art.id)

        # Add Claim nodes
        for idx, claim_data in enumerate(art.semantic_claims):
            claim_text = claim_data.get("claim_text", "")
            if not claim_text:
                continue
            claim_node_id = f"claim:{art.id}:{idx+1}"
            add_node(claim_node_id, "claim", claim_text, art.id)

            # Edge: Artifact SUPPORTS its extracted claim
            g_ref = claim_data.get("grounding_ref", {})
            ev_refs = []
            if g_ref.get("type") and g_ref.get("value"):
                ev_refs.append(EvidenceRef(type=g_ref["type"], value=g_ref["value"]))

            edges.append(
                EvidenceGraphEdge(
                    source_node_id=art_node_id,
                    target_node_id=claim_node_id,
                    relation="SUPPORTS",
                    method="deterministic",
                    confidence_level="high",
                    explanation=f"Extracted claim from {art.display_name}",
                    evidence_refs=ev_refs,
                )
            )

        # Add Entity nodes
        entities = art.metadata.get("entities", {})
        if isinstance(entities, dict):
            for category in ("dates", "locations", "people", "organizations"):
                for ent_val in entities.get(category, []):
                    ent_str = str(ent_val).strip()
                    if not ent_str:
                        continue
                    ent_node_id = f"ent:{category}:{ent_str.lower()}"
                    add_node(ent_node_id, "entity", f"{category.rstrip('s').capitalize()}: {ent_str}")

                    # Edge: Artifact LINKED to Entity
                    edges.append(
                        EvidenceGraphEdge(
                            source_node_id=art_node_id,
                            target_node_id=ent_node_id,
                            relation="LINKED",
                            method="deterministic",
                            confidence_level="medium",
                            explanation=f"Artifact references entity {ent_str}",
                            evidence_refs=[],
                        )
                    )

    # 2. Add Platform Source nodes if present
    for plat_art in case.platform_artifacts:
        plat_node_id = f"platform:{plat_art.platform}:{plat_art.url}"
        add_node(
            plat_node_id,
            "platform_source",
            f"Platform: {plat_art.platform.capitalize()} ({plat_art.title or plat_art.url})",
        )

    # 3. Add Edges from Relations
    for rel in case.relations:
        src_node = f"art:{rel.source_id}"
        tgt_node = f"art:{rel.target_id}"

        # Ensure source and target nodes exist in graph
        if src_node not in existing_node_ids:
            add_node(src_node, "artifact", f"Artifact {rel.source_id}", rel.source_id)
        if tgt_node not in existing_node_ids:
            add_node(tgt_node, "artifact", f"Artifact {rel.target_id}", rel.target_id)

        edges.append(
            EvidenceGraphEdge(
                source_node_id=src_node,
                target_node_id=tgt_node,
                relation=rel.relation,
                method=rel.method,
                confidence_level=rel.confidence_level,
                explanation=rel.explanation or "",
                evidence_refs=rel.evidence_refs,
            )
        )

        # Track explicit contradictions
        if rel.relation == "CONTRADICTS":
            contradiction_list.append({
                "artifact_a": rel.source_id,
                "artifact_b": rel.target_id,
                "conflict_type": rel.conflict_type or "semantic_contradiction",
                "explanation": rel.explanation or "Contradiction detected between artifacts.",
                "method": rel.method,
                "confidence_level": rel.confidence_level,
                "evidence_refs": [ref.model_dump() for ref in rel.evidence_refs],
            })

    return EvidenceGraph(
        nodes=nodes,
        edges=edges,
        contradiction_list=contradiction_list,
    )


def get_supporting_evidence(graph: EvidenceGraph, target_node_id: str) -> List[EvidenceGraphEdge]:
    """Return all edges that support the given target node."""
    return [e for e in graph.edges if e.target_node_id == target_node_id and e.relation == "SUPPORTS"]


def get_contradicting_evidence(graph: EvidenceGraph, target_node_id: str) -> List[EvidenceGraphEdge]:
    """Return all edges that contradict the given target node."""
    return [
        e for e in graph.edges
        if (e.target_node_id == target_node_id or e.source_node_id == target_node_id)
        and e.relation == "CONTRADICTS"
    ]


def get_shared_entities(graph: EvidenceGraph) -> Dict[str, List[str]]:
    """Return map of entity node IDs to list of artifact IDs linking to them."""
    entity_map: Dict[str, List[str]] = {}
    for edge in graph.edges:
        if edge.target_node_id.startswith("ent:") and edge.source_node_id.startswith("art:"):
            ent_id = edge.target_node_id
            art_id = edge.source_node_id[4:]
            entity_map.setdefault(ent_id, []).append(art_id)
    return {k: list(set(v)) for k, v in entity_map.items() if len(set(v)) > 1}
