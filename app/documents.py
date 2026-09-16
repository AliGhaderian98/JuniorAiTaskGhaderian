"""Turn parsed entities into text chunks for embedding and retrieval.

Chunks follow entity boundaries instead of fixed token windows:
- "overview": description, inheritance and relationships to other entities
- "referenced_by": relationships from other entities to this entity
- "attributes": a fixed number of attributes per chunk

Sizes were chosen so that every chunk stays within the embedding model's
512-token input limit (checked in scripts/build_index.py).
"""

from pydantic import BaseModel

from app.models import Entity, Relationship

ATTRIBUTES_PER_CHUNK = 12

# Ownership/audit links that nearly every entity has. They are listed
# separately so they don't crowd out business relationships.
SYSTEM_ATTRIBUTES = {
    "createdBy", "modifiedBy", "createdOnBehalfBy", "modifiedOnBehalfBy",
    "ownerId", "owningUser", "owningTeam", "owningBusinessUnit",
}


class Chunk(BaseModel):
    id: str
    entity_name: str
    chunk_type: str  # "overview", "referenced_by" or "attributes"
    source_path: str
    related_entities: list[str] = []
    text: str


def format_relationship(relationship: Relationship) -> str:
    return (f"{relationship.from_entity}.{relationship.from_attribute} -> "
            f"{relationship.to_entity}.{relationship.to_attribute}")


def is_system_relationship(relationship: Relationship) -> bool:
    return relationship.from_attribute in SYSTEM_ATTRIBUTES


def build_overview_chunk(entity: Entity) -> Chunk:
    business = [r for r in entity.relationships if not is_system_relationship(r)]
    system = [r for r in entity.relationships if is_system_relationship(r)]

    lines = [f"Entity: {entity.name}", f"Description: {entity.description or 'No description.'}"]
    if entity.inheritance_chain:
        lines.append("Inherits from: " + ", ".join(entity.inheritance_chain))
    lines.append(f"Number of attributes: {len(entity.attributes)}")
    lines.append(f"Relationships from {entity.name} to other entities:")
    lines += [f"- {format_relationship(r)}" for r in business] or ["- none"]
    if system:
        targets = sorted({f"{r.from_attribute} -> {r.to_entity}" for r in system})
        lines.append("System ownership/audit relationships: " + ", ".join(targets))
    lines.append(f"Source: {entity.source_path}")

    return Chunk(
        id=f"{entity.name}:overview",
        entity_name=entity.name,
        chunk_type="overview",
        source_path=entity.source_path,
        related_entities=sorted({r.to_entity for r in business} - {entity.name}),
        text="\n".join(lines),
    )


def build_referenced_by_chunk(entity: Entity) -> Chunk | None:
    incoming = [r for r in entity.referenced_by if not is_system_relationship(r)]
    if not incoming:
        return None

    lines = [f"Entity: {entity.name}", f"Relationships from other entities to {entity.name}:"]
    lines += [f"- {format_relationship(r)}" for r in incoming]
    return Chunk(
        id=f"{entity.name}:referenced_by",
        entity_name=entity.name,
        chunk_type="referenced_by",
        source_path=entity.source_path,
        related_entities=sorted({r.from_entity for r in incoming} - {entity.name}),
        text="\n".join(lines),
    )


def build_attribute_chunks(entity: Entity) -> list[Chunk]:
    attributes = entity.attributes
    batches = [attributes[i:i + ATTRIBUTES_PER_CHUNK] for i in range(0, len(attributes), ATTRIBUTES_PER_CHUNK)]

    chunks = []
    for number, batch in enumerate(batches, start=1):
        lines = [f"Entity: {entity.name}",
                 f"Attributes (part {number} of {len(batches)}):"]
        for attribute in batch:
            line = f"- {attribute.name} ({attribute.data_type})"
            if attribute.description:
                line += f": {attribute.description}"
            lines.append(line)
        chunks.append(Chunk(
            id=f"{entity.name}:attributes:{number}",
            entity_name=entity.name,
            chunk_type="attributes",
            source_path=entity.source_path,
            text="\n".join(lines),
        ))
    return chunks


def build_chunks(entities: list[Entity]) -> list[Chunk]:
    chunks = []
    for entity in entities:
        chunks.append(build_overview_chunk(entity))
        referenced_by = build_referenced_by_chunk(entity)
        if referenced_by:
            chunks.append(referenced_by)
        chunks.extend(build_attribute_chunks(entity))
    return chunks
