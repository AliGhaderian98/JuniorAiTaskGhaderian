"""Normalized CDM data models used by the parser and the retrieval pipeline."""

from pydantic import BaseModel


class Attribute(BaseModel):
    name: str
    data_type: str
    description: str = ""
    source_path: str  # CDM file that defines this attribute


class Relationship(BaseModel):
    from_entity: str
    from_attribute: str
    to_entity: str
    to_attribute: str


class Entity(BaseModel):
    name: str
    description: str = ""
    source_path: str  # the most specific file (e.g. the banking Account)
    inheritance_chain: list[str] = []  # parent files, nearest parent first
    attributes: list[Attribute] = []
    relationships: list[Relationship] = []  # outgoing: this entity -> other
    referenced_by: list[Relationship] = []  # incoming: other -> this entity
