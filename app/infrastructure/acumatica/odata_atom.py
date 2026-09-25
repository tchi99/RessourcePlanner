from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Final
import xml.etree.ElementTree as ET


ATOM_NAMESPACE: Final = "http://www.w3.org/2005/Atom"
DATA_NAMESPACE: Final = "http://schemas.microsoft.com/ado/2007/08/dataservices"
METADATA_NAMESPACE: Final = "http://schemas.microsoft.com/ado/2007/08/dataservices/metadata"
XML_NAMESPACE: Final = "http://www.w3.org/XML/1998/namespace"


def normalize_text(value: object) -> str:
    """Normalize textual OData values without exposing them in diagnostics."""

    return str(value or "").strip()


def optional_text(value: object) -> str | None:
    text = normalize_text(value)
    return text or None


def classify_http_failure(status_code: int) -> tuple[str, bool]:
    """Return the stable failure category and retryability used by Acumatica adapters."""

    if status_code == 401:
        return "authentication", False
    if status_code == 403:
        return "authorization", False
    if status_code == 429:
        return "throttled", True
    if status_code >= 500:
        return "upstream_5xx", True
    return "http_error", False


class ODataAtomFeedError(ValueError):
    """Structural Atom/OData contract error without retaining business values."""

    def __init__(
        self,
        reason: str,
        *,
        entry_index: int | None = None,
    ) -> None:
        self.reason = reason
        self.entry_index = entry_index
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class ODataAtomProperty:
    name: str
    value: str | None
    edm_type: str | None
    is_null: bool
    preserves_space: bool


@dataclass(frozen=True, slots=True)
class ODataAtomEntry:
    properties: tuple[ODataAtomProperty, ...]
    entity_type: str | None = None
    has_self_link: bool = False

    def values(self) -> dict[str, str | None]:
        return {prop.name: prop.value for prop in self.properties}


@dataclass(frozen=True, slots=True)
class ODataAtomFeed:
    title: str | None
    namespaces: tuple[tuple[str, str], ...]
    entries: tuple[ODataAtomEntry, ...]

    @property
    def entity_types(self) -> tuple[str, ...]:
        seen: list[str] = []
        for entry in self.entries:
            if entry.entity_type and entry.entity_type not in seen:
                seen.append(entry.entity_type)
        return tuple(seen)

    @property
    def has_self_links(self) -> bool:
        return any(entry.has_self_link for entry in self.entries)


def _payload_bytes(xml_payload: bytes | str) -> bytes:
    if isinstance(xml_payload, bytes):
        return xml_payload
    if isinstance(xml_payload, str):
        return xml_payload.encode("utf-8")
    raise ODataAtomFeedError("invalid_xml")


def _local_name(tag: str) -> str:
    if tag.startswith("{") and "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _read_namespaces(payload: bytes) -> tuple[tuple[str, str], ...]:
    namespaces: list[tuple[str, str]] = []
    try:
        for _event, namespace in ET.iterparse(BytesIO(payload), events=("start-ns",)):
            prefix, uri = namespace
            item = (prefix or "", uri)
            if item not in namespaces:
                namespaces.append(item)
    except (ET.ParseError, TypeError, ValueError) as exc:
        raise ODataAtomFeedError("invalid_xml") from exc
    return tuple(namespaces)


def _entry_entity_type(entry: ET.Element) -> str | None:
    for category in entry.findall(f".//{{{ATOM_NAMESPACE}}}category"):
        term = optional_text(category.attrib.get("term"))
        if term:
            return term
    return None


def _entry_has_self_link(entry: ET.Element) -> bool:
    return any(
        normalize_text(link.attrib.get("rel")).casefold() == "self"
        for link in entry.findall(f".//{{{ATOM_NAMESPACE}}}link")
    )


def _entry_properties(
    properties: ET.Element,
) -> tuple[ODataAtomProperty, ...]:
    rows: list[ODataAtomProperty] = []
    for element in list(properties):
        if not element.tag.startswith(f"{{{DATA_NAMESPACE}}}"):
            continue
        is_null = (
            normalize_text(
                element.attrib.get(f"{{{METADATA_NAMESPACE}}}null")
            ).casefold()
            == "true"
        )
        rows.append(
            ODataAtomProperty(
                name=_local_name(element.tag),
                value=None if is_null else optional_text(element.text),
                edm_type=optional_text(
                    element.attrib.get(f"{{{METADATA_NAMESPACE}}}type")
                ),
                is_null=is_null,
                preserves_space=(
                    normalize_text(
                        element.attrib.get(f"{{{XML_NAMESPACE}}}space")
                    ).casefold()
                    == "preserve"
                ),
            )
        )
    return tuple(rows)


def parse_atom_feed(xml_payload: bytes | str) -> ODataAtomFeed:
    """Parse the common Atom/OData envelope without applying entity-specific rules."""

    payload = _payload_bytes(xml_payload)
    namespaces = _read_namespaces(payload)
    try:
        root = ET.fromstring(payload)
    except (ET.ParseError, TypeError, ValueError) as exc:
        raise ODataAtomFeedError("invalid_xml") from exc
    if root.tag != f"{{{ATOM_NAMESPACE}}}feed":
        raise ODataAtomFeedError("invalid_feed_root")

    title = optional_text(root.findtext(f"{{{ATOM_NAMESPACE}}}title"))
    entries: list[ODataAtomEntry] = []
    for entry_index, entry in enumerate(root.findall(f".//{{{ATOM_NAMESPACE}}}entry")):
        properties = entry.find(f".//{{{METADATA_NAMESPACE}}}properties")
        if properties is None:
            raise ODataAtomFeedError(
                "properties_missing",
                entry_index=entry_index,
            )
        entries.append(
            ODataAtomEntry(
                properties=_entry_properties(properties),
                entity_type=_entry_entity_type(entry),
                has_self_link=_entry_has_self_link(entry),
            )
        )
    return ODataAtomFeed(
        title=title,
        namespaces=namespaces,
        entries=tuple(entries),
    )
