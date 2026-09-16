"""Parse local CDM JSON files into normalized Entity objects.

All paths are relative to the data directory (the CDM "schemaDocuments" root)
and use forward slashes, like CDM corpus paths.
"""

import json
import posixpath
from pathlib import Path

from app.cdm_loader import ENTITY_FILES, MANIFEST_FILES
from app.models import Attribute, Entity, Relationship


def load_json(data_dir: Path, path: str) -> dict:
    with open(data_dir / path, encoding="utf-8") as f:
        return json.load(f)


def find_entity_definition(document: dict, path: str) -> dict:
    for definition in document.get("definitions", []):
        if "entityName" in definition:
            return definition
    raise ValueError(f"No entity definition found in {path}")


def parse_attribute(member: dict | str, source_path: str) -> Attribute | None:
    """Convert one attribute from 'hasAttributes' into an Attribute.

    Returns None for string members: those point to attribute groups
    (e.g. "customerIdAttribute") that are defined outside the indexed files.
    """
    if isinstance(member, str):
        return None

    if "entity" in member:
        data_type = "lookup -> " + " | ".join(lookup_targets(member["entity"]))
    elif isinstance(member.get("dataType"), dict):
        data_type = member["dataType"].get("dataTypeReference", "unknown")
    else:
        data_type = member.get("dataType", "unknown")

    return Attribute(
        name=member["name"],
        data_type=data_type,
        description=member.get("description", "").strip(),
        source_path=source_path,
    )


def lookup_targets(entity_attribute: dict) -> list[str]:
    """Target entity names of a lookup. Polymorphic lookups have several options."""
    reference = entity_attribute.get("entityReference")
    if isinstance(reference, str):
        return [reference]
    if isinstance(reference, dict):
        return [option["entity"]["entityReference"] for option in reference.get("hasAttributes", [])]
    return ["unknown"]


def parse_own_attributes(definition: dict, source_path: str) -> list[Attribute]:
    """Attributes declared directly in one entity definition (not inherited ones)."""
    attributes = []
    for item in definition.get("hasAttributes", []):
        if isinstance(item, dict) and "attributeGroupReference" in item:
            members = item["attributeGroupReference"].get("members", [])
        else:
            members = [item]
        for member in members:
            attribute = parse_attribute(member, source_path)
            if attribute:
                attributes.append(attribute)
    return attributes


def find_parent_path(data_dir: Path, path: str, extends_entity: object) -> str | None:
    """Resolve 'base_Account/Account' to the parent file path, or None at the root.

    The moniker ('base_Account') is defined in the _allImports.cdm.json file
    next to the child entity. Root types such as 'CdsStandard' have no '/'.
    """
    if not isinstance(extends_entity, str) or "/" not in extends_entity:
        return None

    moniker = extends_entity.split("/")[0]
    imports_path = posixpath.join(posixpath.dirname(path), "_allImports.cdm.json")
    for item in load_json(data_dir, imports_path).get("imports", []):
        if item.get("moniker") == moniker:
            return item["corpusPath"].lstrip("/")
    raise ValueError(f"Moniker '{moniker}' used in {path} not found in {imports_path}")


def load_entity(data_dir: Path, path: str) -> Entity:
    """Load an entity and merge in the attributes of all its parent definitions."""
    layers = []  # (path, definition), child first
    current_path = path
    while current_path and current_path not in [p for p, _ in layers]:
        definition = find_entity_definition(load_json(data_dir, current_path), current_path)
        layers.append((current_path, definition))
        current_path = find_parent_path(data_dir, current_path, definition.get("extendsEntity"))

    # Walk from the root parent down to the child. A dict keeps the first
    # position of each name, while a child layer replaces the parent's value.
    attributes_by_name: dict[str, Attribute] = {}
    for layer_path, definition in reversed(layers):
        for attribute in parse_own_attributes(definition, layer_path):
            attributes_by_name[attribute.name] = attribute

    description = next((d.get("description", "") for _, d in layers if d.get("description")), "")
    return Entity(
        name=layers[0][1]["entityName"],
        description=description.strip(),
        source_path=path,
        inheritance_chain=[p for p, _ in layers[1:]],
        attributes=list(attributes_by_name.values()),
    )


def parse_manifest_relationships(
    data_dir: Path, manifest_path: str, entity_paths: set[str]
) -> list[Relationship]:
    """Read explicit relationships from a manifest.

    Only relationships that start at an indexed entity file are kept.
    Manifest paths are relative to the manifest's own folder.
    """
    manifest = load_json(data_dir, manifest_path)
    manifest_dir = posixpath.dirname(manifest_path)

    relationships = []
    for item in manifest.get("relationships", []):
        from_file, from_entity = item["fromEntity"].rsplit("/", 1)
        if posixpath.join(manifest_dir, from_file) not in entity_paths:
            continue
        relationships.append(Relationship(
            from_entity=from_entity,
            from_attribute=item["fromEntityAttribute"],
            to_entity=item["toEntity"].rsplit("/", 1)[1],
            to_attribute=item["toEntityAttribute"],
        ))
    return relationships


def load_entities(data_dir: Path, entity_paths: list[str], manifest_paths: list[str]) -> list[Entity]:
    """Load all entities and attach outgoing and incoming relationships."""
    entities = [load_entity(data_dir, path) for path in entity_paths]
    by_name = {entity.name: entity for entity in entities}
    if len(by_name) != len(entities):
        raise ValueError("Entity names must be unique within the indexed scope")

    # The same relationship can appear twice: in two manifests, or with two
    # different target files that have the same entity name (e.g. two "User" files).
    seen = set()
    for manifest_path in manifest_paths:
        for relationship in parse_manifest_relationships(data_dir, manifest_path, set(entity_paths)):
            key = (relationship.from_entity, relationship.from_attribute,
                   relationship.to_entity, relationship.to_attribute)
            if key in seen:
                continue
            seen.add(key)
            by_name[relationship.from_entity].relationships.append(relationship)
            if relationship.to_entity in by_name:
                by_name[relationship.to_entity].referenced_by.append(relationship)
    return entities


def load_cdm_entities(data_dir: Path) -> list[Entity]:
    """Load the pinned banking + common scope (see app/cdm_loader.py)."""
    return load_entities(data_dir, ENTITY_FILES, MANIFEST_FILES)
