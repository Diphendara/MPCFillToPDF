"""Business-logic validation for MPCFill XML files.

Runs checks that go beyond parse-level errors (which the parser already
catches with descriptive messages).  Returns a list of `ValidationWarning`
objects so callers can decide whether to abort or ask the user to confirm.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from src.parser import parse

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ValidationWarning:
    code: str  # machine-readable key
    message: str  # human-readable description (Spanish)


def validate(xml_path: str | Path) -> list[ValidationWarning]:
    """Parse *xml_path* and return all business-logic warnings found.

    A parse failure itself is returned as a single warning with
    code="parse_error" so callers always get a list (never an exception).
    An empty list means the file is valid.
    """
    xml_path = Path(xml_path)
    warnings: list[ValidationWarning] = []

    try:
        order = parse(xml_path)
    except Exception as exc:
        return [ValidationWarning("parse_error", f"Error al parsear el XML: {exc}")]

    if not order.fronts:
        warnings.append(
            ValidationWarning(
                "no_fronts",
                "El XML no contiene ninguna carta en <fronts>",
            )
        )
        return warnings  # further slot checks would be meaningless

    # --- front-slot uniqueness -----------------------------------------------
    front_slot_to_name: dict[int, str] = {}
    for card in order.fronts:
        for slot in card.slots:
            if slot in front_slot_to_name:
                warnings.append(
                    ValidationWarning(
                        "duplicate_front_slot",
                        f"El slot {slot} aparece en más de una carta en <fronts>: "
                        f"«{front_slot_to_name[slot]}» y «{card.name}»",
                    )
                )
            else:
                front_slot_to_name[slot] = card.name

    # --- back-slot uniqueness ------------------------------------------------
    back_slot_to_name: dict[int, str] = {}
    for card in order.backs:
        for slot in card.slots:
            if slot in back_slot_to_name:
                warnings.append(
                    ValidationWarning(
                        "duplicate_back_slot",
                        f"El slot {slot} aparece en más de una carta en <backs>: "
                        f"«{back_slot_to_name[slot]}» y «{card.name}»",
                    )
                )
            else:
                back_slot_to_name[slot] = card.name

    # --- orphan back slots (back with no matching front) ---------------------
    for slot, name in back_slot_to_name.items():
        if slot not in front_slot_to_name:
            warnings.append(
                ValidationWarning(
                    "orphan_back_slot",
                    f"El slot {slot} está en <backs> («{name}») pero no tiene "
                    "carta correspondiente en <fronts>",
                )
            )

    # --- empty cardback ------------------------------------------------------
    if not order.cardback_id:
        warnings.append(
            ValidationWarning(
                "empty_cardback",
                "El elemento <cardback> está vacío o falta en el XML",
            )
        )

    if warnings:
        _log.debug("validate %s: %d warning(s)", xml_path.name, len(warnings))
    return warnings
