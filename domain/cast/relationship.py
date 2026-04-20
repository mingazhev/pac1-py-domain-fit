from __future__ import annotations

import re
from enum import Enum
from typing import Any


class CastRelationship(str, Enum):
    ASSISTANT_PROTOTYPE = "assistant_prototype"
    BOSS = "boss"
    BUREAU_LEAD = "bureau_lead"
    CAT = "cat"
    CHILD = "child"
    CONSULTING_CLIENT = "consulting_client"
    DAUGHTER = "daughter"
    DAY_JOB_CEO = "day_job_ceo"
    DEVICE = "device"
    DOG = "dog"
    ENGINEERING_COUNTERPART = "engineering_counterpart"
    FATHER_IN_LAW = "father_in_law"
    HEALTH_FRIEND = "health_friend"
    HOME_SERVER = "home_server"
    HOUSE_SERVER = "house_server"
    HUSBAND = "husband"
    LAB_SERVER = "lab_server"
    MAKER_FRIEND = "maker_friend"
    MOTHER_IN_LAW = "mother_in_law"
    OPS_LEAD = "ops_lead"
    PARTNER = "partner"
    PET = "pet"
    PRINTER = "printer"
    PRODUCT_MANAGER = "product_manager"
    SELF = "self"
    SON = "son"
    SPOUSE = "spouse"
    STARTUP_ADVISOR = "startup_advisor"
    STARTUP_PARTNER = "startup_partner"
    WIFE = "wife"


def normalize_cast_relationship_label(value: Any) -> str:
    normalized = re.sub(r"[_\-\s]+", "_", str(value or "").strip().lower()).strip("_")
    return normalized


def parse_cast_relationship(value: Any) -> CastRelationship | None:
    normalized = normalize_cast_relationship_label(value)
    if not normalized:
        return None
    for member in CastRelationship:
        if member.value == normalized:
            return member
    return None


def normalize_cast_relationship(value: Any) -> str:
    parsed = parse_cast_relationship(value)
    if parsed is not None:
        return parsed.value
    return normalize_cast_relationship_label(value)


def expand_cast_relationship_aliases(value: Any) -> tuple[str, ...]:
    normalized = str(value or "").strip()
    if not normalized:
        return ()

    variants = [normalized]
    space_variant = re.sub(r"[_\-]+", " ", normalized).strip()
    if space_variant:
        variants.append(space_variant)
    canonical = normalize_cast_relationship(value)
    if canonical and canonical != normalized and canonical != space_variant:
        variants.append(canonical)

    possessive_variants: list[str] = []
    for variant in variants:
        stripped_variant = variant.strip()
        if not stripped_variant:
            continue
        if stripped_variant.endswith("'") or stripped_variant.endswith("'s"):
            possessive_variants.append(stripped_variant)
        elif stripped_variant.endswith("s"):
            possessive_variants.append(f"{stripped_variant}'")
        else:
            possessive_variants.append(f"{stripped_variant}'s")
    variants.extend(possessive_variants)

    return tuple(dict.fromkeys(variant for variant in variants if variant))


def parse_cast_relationship_strict(value: Any) -> CastRelationship:
    parsed = parse_cast_relationship(value)
    if parsed is None:
        raise ValueError(
            f"cast relationship {value!r} is not in the controlled vocabulary"
        )
    return parsed


def is_controlled_cast_relationship(value: Any) -> bool:
    return parse_cast_relationship(value) is not None
