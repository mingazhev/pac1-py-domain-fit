from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import date, datetime, timezone

from domain.cast import (
    Animal,
    CastEntity,
    CastMilestone,
    Device,
    EntityKind,
    Person,
    Pet,
    Service,
    System,
    classify_important_date_label,
    resolve_cast_contact_policy,
)
from domain.cast.relationship import (
    expand_cast_relationship_aliases,
    normalize_cast_relationship,
)
from formats.markdown_records import (
    extract_markdown_bullet_values,
    parse_markdown_record_fields,
)
def _coerce_strings(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(",")]
        return tuple(part for part in parts if part)
    if isinstance(value, (list, tuple)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


def _parse_iso_date(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        return None


def _extract_markdown_named_date_entries(
    text: str, key: str
) -> tuple[CastMilestone, ...]:
    lines = text.splitlines()
    milestones: list[CastMilestone] = []
    pattern = f"- {key.lower()}:"
    index = 0
    while index < len(lines):
        raw_line = lines[index]
        stripped = raw_line.strip()
        if not stripped.lower().startswith(pattern):
            index += 1
            continue
        current_indent = len(raw_line) - len(raw_line.lstrip(" \t"))
        look_ahead = index + 1
        while look_ahead < len(lines):
            nested_line = lines[look_ahead]
            stripped_nested = nested_line.strip()
            if not stripped_nested:
                look_ahead += 1
                continue
            nested_indent = len(nested_line) - len(nested_line.lstrip(" \t"))
            if nested_indent <= current_indent:
                break
            if not stripped_nested.startswith("- "):
                look_ahead += 1
                continue
            item = stripped_nested[2:].strip()
            match = re.match(
                r"^`?([a-z0-9_\- ]+)`?\s*:\s*`?(\d{4}-\d{2}-\d{2})`?(?:\s+-.*)?$",
                item,
                re.IGNORECASE,
            )
            if match is not None:
                label = re.sub(
                    r"[^a-z0-9]+", "_", match.group(1).strip().lower()
                ).strip("_")
                occurred_on = match.group(2).strip()
                if label and occurred_on:
                    milestones.append(
                        CastMilestone(
                            label=label,
                            occurred_on=occurred_on,
                            kind=_important_date_kind(label),
                        )
                    )
            look_ahead += 1
        index = look_ahead
    return tuple(dict.fromkeys(milestones))


def _important_date_kind(label: object) -> str:
    return classify_important_date_label(label).value


def _coerce_milestones(value: object) -> tuple[CastMilestone, ...]:
    milestones: list[CastMilestone] = []
    if isinstance(value, CastMilestone):
        return (value,)
    if isinstance(value, Mapping):
        label = str(value.get("label") or value.get("name") or "").strip()
        occurred_on = str(value.get("occurred_on") or value.get("date") or "").strip()
        kind = str(value.get("kind") or "").strip() or _important_date_kind(label)
        if label and occurred_on:
            return (CastMilestone(label=label, occurred_on=occurred_on, kind=kind),)
        return ()
    if isinstance(value, (list, tuple)):
        for item in value:
            if isinstance(item, CastMilestone):
                milestones.append(item)
                continue
            if isinstance(item, Mapping):
                label = str(item.get("label") or item.get("name") or "").strip()
                occurred_on = str(
                    item.get("occurred_on") or item.get("date") or ""
                ).strip()
                kind = str(item.get("kind") or "").strip() or _important_date_kind(label)
                if label and occurred_on:
                    milestones.append(
                        CastMilestone(label=label, occurred_on=occurred_on, kind=kind)
                    )
                continue
            if isinstance(item, tuple) and len(item) == 2:
                label = str(item[0] or "").strip()
                occurred_on = str(item[1] or "").strip()
                if label and occurred_on:
                    milestones.append(
                        CastMilestone(
                            label=label,
                            occurred_on=occurred_on,
                            kind=_important_date_kind(label),
                        )
                    )
    return tuple(dict.fromkeys(milestones))


def _age_on_date(birthday: datetime, reference_date: date) -> int:
    years = reference_date.year - birthday.year
    if (reference_date.month, reference_date.day) < (birthday.month, birthday.day):
        years -= 1
    return years


def _relationship_descriptor_terms(entity: CastEntity) -> tuple[str, ...]:
    relationship = entity.normalized_relationship
    if relationship in {"wife", "husband", "spouse", "partner"}:
        return ("spouse", "partner")
    if relationship == "engineering counterpart":
        return ("infra counterpart", "platform counterpart")
    return ()


def _child_life_stage_descriptors(
    entity: CastEntity,
    *,
    birthday: datetime,
    reference_date: date,
) -> tuple[str, ...]:
    if entity.normalized_relationship not in {"son", "daughter", "child"}:
        return ()

    age = _age_on_date(birthday, reference_date)
    descriptors: list[str] = []

    if 3 <= age <= 4:
        descriptors.append("preschool-age child")
    if 3 <= age <= 5:
        descriptors.append("kindergarten-age child")
    if 6 <= age <= 17:
        descriptors.append("school-age child")

    return tuple(dict.fromkeys(descriptor for descriptor in descriptors if descriptor))


def _cast_entity_class_for(
    *,
    kind: EntityKind | None,
    relationship: str,
    birthday: str | None,
) -> type[CastEntity]:
    normalized_relationship = re.sub(
        r"[_\\-]+", " ", normalize_cast_relationship(relationship)
    ).strip()
    if kind is EntityKind.SYSTEM:
        return System
    if kind is EntityKind.DEVICE:
        return Device
    if kind is EntityKind.SERVICE:
        return Service
    if kind is EntityKind.ANIMAL:
        return Animal
    if kind is EntityKind.PET:
        return Pet
    if normalized_relationship in {"dog", "cat", "pet"}:
        return Pet
    if birthday:
        return Person
    return Person


def cast_entity_from_mapping(raw: Mapping[str, object]) -> CastEntity | None:
    path = str(raw.get("path") or "").strip()
    title = str(raw.get("title") or "").strip()
    entity_slug = str(raw.get("entity_slug") or "").strip()
    if not title and not entity_slug:
        return None
    alias_terms = tuple(
        str(alias).strip() for alias in raw.get("alias_terms", ()) if str(alias).strip()
    )
    birthday = str(raw.get("birthday") or "").strip() or None
    created_on = str(raw.get("created_on") or "").strip() or None
    milestones = tuple(
        dict.fromkeys(
            (
                *_coerce_milestones(raw.get("important_dates")),
                *_coerce_milestones(raw.get("milestones")),
            )
        )
    )
    kind = EntityKind.parse(raw.get("kind"))
    relationship = normalize_cast_relationship(raw.get("relationship"))
    entity_cls = _cast_entity_class_for(
        kind=kind, relationship=relationship, birthday=birthday
    )
    payload = dict(
        path=path,
        title=title or entity_slug,
        entity_id=str(raw.get("entity_id") or "").strip(),
        entity_slug=entity_slug,
        alias=str(raw.get("alias") or "").strip(),
        kind=kind,
        relationship=relationship,
        primary_contact_email=str(
            raw.get("primary_contact_email") or raw.get("email") or ""
        ).strip(),
        created_on=created_on,
        milestones=milestones,
        identity_terms=tuple(
            str(term).strip()
            for term in raw.get("identity_terms", ())
            if str(term).strip()
        ),
        alias_terms=alias_terms,
        descriptor_terms=tuple(
            str(term).strip()
            for term in raw.get("descriptor_terms", ())
            if str(term).strip()
        ),
        body=str(raw.get("body") or "").strip(),
    )
    if issubclass(entity_cls, (Person, Pet, Animal)):
        payload["birthday"] = birthday
    return entity_cls(**payload)


def cast_entities_from_mappings(
    raw_records: Sequence[Mapping[str, object]],
) -> tuple[CastEntity, ...]:
    entities = tuple(
        entity
        for entity in (cast_entity_from_mapping(raw) for raw in raw_records)
        if entity is not None
    )
    return _enrich_cast_entities(entities)


def cast_entity_to_mapping(entity: CastEntity) -> dict[str, object]:
    payload: dict[str, object] = {
        "path": entity.path,
        "title": entity.title,
        "entity_id": entity.entity_id,
        "entity_slug": entity.entity_slug,
        "alias": entity.alias,
        "relationship": entity.relationship,
        "primary_contact_email": entity.primary_contact_email,
        "email": entity.primary_contact_email,
        "identity_terms": entity.identity_terms,
        "alias_terms": entity.alias_terms,
        "descriptor_terms": entity.descriptor_terms,
        "body": entity.body,
    }
    if entity.kind is not None:
        payload["kind"] = entity.kind.value
    if entity.birthday:
        payload["birthday"] = entity.birthday
    if entity.created_on:
        payload["created_on"] = entity.created_on
    if entity.important_dates:
        payload["important_dates"] = tuple(
            {
                "label": milestone.label,
                "occurred_on": milestone.occurred_on,
                "kind": milestone.kind,
            }
            for milestone in entity.important_dates
        )
    return payload
def build_cast_entities(
    raw_records: Sequence[Mapping[str, object]],
    *,
    reference_date: date | None = None,
) -> tuple[CastEntity, ...]:
    effective_reference_date = reference_date or datetime.now(timezone.utc).date()
    base_entities: list[CastEntity] = []

    for raw in raw_records:
        path = str(raw.get("path") or "").strip()
        stem = path.rsplit("/", 1)[-1].rsplit(".", 1)[0].strip()
        if not stem:
            continue
        raw_body = str(raw.get("body") or "")
        record_fields = parse_markdown_record_fields(raw_body)
        body = record_fields.body
        frontmatter = record_fields.fields
        title = str(raw.get("title") or frontmatter.get("title") or "").strip() or stem
        frontmatter_id = str(
            raw.get("entity_id") or frontmatter.get("entity_id") or f"entity.{stem}"
        ).strip()

        aliases = list(_coerce_strings(raw.get("alias_terms")))
        aliases.extend(_coerce_strings(frontmatter.get("alias_terms")))
        aliases.extend(_coerce_strings(raw.get("alias")))
        aliases.extend(_coerce_strings(frontmatter.get("alias")))
        aliases.extend(extract_markdown_bullet_values(body, "alias"))
        aliases.append(title)

        relationships = list(_coerce_strings(raw.get("relationship")))
        relationships.extend(_coerce_strings(frontmatter.get("relationship")))
        relationships.extend(extract_markdown_bullet_values(body, "relationship"))
        relationship = normalize_cast_relationship(relationships[0] if relationships else "")
        for relationship_value in relationships:
            aliases.extend(expand_cast_relationship_aliases(relationship_value))

        primary_contact_emails = list(_coerce_strings(raw.get("primary_contact_email")))
        primary_contact_emails.extend(
            _coerce_strings(frontmatter.get("primary_contact_email"))
        )
        primary_contact_emails.extend(
            extract_markdown_bullet_values(body, "primary_contact_email")
        )
        primary_contact_email = (
            primary_contact_emails[0] if primary_contact_emails else ""
        )

        kinds = list(_coerce_strings(raw.get("kind")))
        kinds.extend(_coerce_strings(frontmatter.get("kind")))
        kinds.extend(extract_markdown_bullet_values(body, "kind"))
        kind = (
            EntityKind.parse(kinds[0]) if kinds else EntityKind.parse(raw.get("kind"))
        )

        birthdays = list(_coerce_strings(raw.get("birthday")))
        birthdays.extend(_coerce_strings(frontmatter.get("birthday")))
        birthdays.extend(extract_markdown_bullet_values(body, "birthday"))
        birthday = (
            birthdays[0]
            if birthdays
            else str(raw.get("birthday") or frontmatter.get("birthday") or "").strip() or None
        )

        created_on_values = list(_coerce_strings(raw.get("created_on")))
        created_on_values.extend(_coerce_strings(frontmatter.get("created_on")))
        created_on_values.extend(extract_markdown_bullet_values(body, "created_on"))
        created_on = (
            created_on_values[0]
            if created_on_values
            else str(raw.get("created_on") or frontmatter.get("created_on") or "").strip() or None
        )
        milestones = tuple(
            dict.fromkeys(
                (
                    *_coerce_milestones(frontmatter.get("important_dates")),
                    *_coerce_milestones(frontmatter.get("milestones")),
                    *_coerce_milestones(raw.get("milestones")),
                    *_extract_markdown_named_date_entries(body, "important_dates"),
                    *_extract_markdown_named_date_entries(body, "milestones"),
                )
            )
        )
        if not created_on:
            created_on = next(
                (
                    milestone.occurred_on
                    for milestone in milestones
                    if milestone.label == "created_on"
                ),
                None,
            )
        if not birthday:
            birthday = next(
                (
                    milestone.occurred_on
                    for milestone in milestones
                    if milestone.label == "birthday"
                ),
                None,
            )

        if frontmatter_id:
            aliases.append(frontmatter_id)
            aliases.append(frontmatter_id.split(".", 1)[-1])

        identity_terms = tuple(
            dict.fromkeys(
                term
                for term in (
                    *_coerce_strings(raw.get("identity_terms")),
                    *_coerce_strings(raw.get("alias")),
                    *extract_markdown_bullet_values(body, "alias"),
                    title,
                    frontmatter_id,
                    frontmatter_id.split(".", 1)[-1] if frontmatter_id else "",
                    stem,
                )
                if str(term).strip()
            )
        )

        entity = cast_entity_from_mapping(
            {
                "path": path,
                "title": title,
                "entity_id": frontmatter_id,
                "entity_slug": stem,
                "alias": str(raw.get("alias") or "").strip(),
                "kind": kind.value if kind is not None else "",
                "relationship": relationship,
                "birthday": birthday or "",
                "created_on": created_on or "",
                "milestones": milestones,
                "primary_contact_email": primary_contact_email,
                "identity_terms": identity_terms,
                "alias_terms": tuple(
                    dict.fromkeys(alias for alias in aliases if str(alias).strip())
                ),
                "body": body.strip(),
            }
        )
        if entity is not None:
            base_entities.append(entity)

    return _enrich_cast_entities(
        tuple(base_entities),
        reference_date=effective_reference_date,
    )


def _enrich_cast_entities(
    entities: Sequence[CastEntity],
    *,
    reference_date: date | None = None,
) -> tuple[CastEntity, ...]:
    if not entities:
        return ()
    effective_reference_date = reference_date or datetime.now(timezone.utc).date()
    enriched_entities = list(entities)
    children: list[tuple[datetime, int]] = []
    for index, entity in enumerate(enriched_entities):
        if (
            entity.normalized_relationship not in {"son", "daughter", "child"}
            or not entity.birthday
        ):
            continue
        birthday = _parse_iso_date(entity.birthday)
        if birthday is None:
            continue
        children.append((birthday, index))
        life_stage_descriptors = _child_life_stage_descriptors(
            entity,
            birthday=birthday,
            reference_date=effective_reference_date,
        )
        if life_stage_descriptors:
            enriched_entities[index] = replace(
                entity,
                descriptor_terms=tuple(
                    dict.fromkeys((*entity.descriptor_terms, *life_stage_descriptors))
                ),
            )

    if len(children) >= 2:
        children.sort()
        relative_enrichment = {
            children[0][1]: {
                "descriptor_terms": ("older child",),
                "alias_terms": ("older one",),
            },
            children[-1][1]: {
                "descriptor_terms": ("younger child",),
                "alias_terms": ("younger one",),
            },
        }
        for index, additions in relative_enrichment.items():
            entity = enriched_entities[index]
            enriched_entities[index] = replace(
                entity,
                descriptor_terms=tuple(
                    dict.fromkeys(
                        (*entity.descriptor_terms, *additions["descriptor_terms"])
                    )
                ),
                alias_terms=tuple(
                    dict.fromkeys((*entity.alias_terms, *additions["alias_terms"]))
                ),
            )

    for index, entity in enumerate(enriched_entities):
        relationship_descriptors = _relationship_descriptor_terms(entity)
        if not relationship_descriptors:
            continue
        enriched_entities[index] = replace(
            entity,
            descriptor_terms=tuple(
                dict.fromkeys((*entity.descriptor_terms, *relationship_descriptors))
            ),
        )

    return tuple(enriched_entities)


def resolve_cast_entity_by_email(
    entities: Sequence[CastEntity],
    sender_email: str,
) -> CastEntity | None:
    normalized_sender = sender_email.strip().lower()
    if not normalized_sender:
        return None
    matches = [entity for entity in entities if entity.matches_email(normalized_sender)]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        return None
    expected_matches = [
        entity
        for entity in matches
        if resolve_cast_contact_policy(entity).canonical_email_expected
    ]
    if len(expected_matches) == 1:
        return expected_matches[0]
    return None
