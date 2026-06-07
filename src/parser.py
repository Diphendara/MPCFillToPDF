import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

_log = logging.getLogger(__name__)


@dataclass
class CardImage:
    drive_id: str
    name: str
    slots: list[int]


@dataclass
class CardOrder:
    quantity: int
    fronts: list[CardImage]
    backs: list[CardImage]
    cardback_id: str

    def back_for_slot(self, slot: int) -> str:
        """Return the Drive ID of the back image for a given slot."""
        for card in self.backs:
            if slot in card.slots:
                return card.drive_id
        return self.cardback_id

    def all_drive_ids(self) -> set[str]:
        """Return every unique Drive ID in the order (fronts + backs + default cardback)."""
        ids = {self.cardback_id}
        for card in self.fronts + self.backs:
            ids.add(card.drive_id)
        return ids


def _parse_slots(slots_text: str) -> list[int]:
    return [int(s.strip()) for s in slots_text.split(",") if s.strip()]


def parse(xml_path: str | Path) -> CardOrder:
    _log.debug("Parsing %s", xml_path)
    try:
        tree = ET.parse(xml_path)
    except ET.ParseError as exc:
        raise ValueError(f"XML inválido en '{xml_path}': {exc}") from exc
    root = tree.getroot()

    details = root.find("details")
    quantity = int(details.findtext("quantity", default="0"))

    def parse_cards(section_tag: str) -> list[CardImage]:
        section = root.find(section_tag)
        if section is None:
            return []
        cards = []
        for card_el in section.findall("card"):
            drive_id = card_el.findtext("id", "").strip()
            name = card_el.findtext("name", "").strip()
            slots_text = card_el.findtext("slots", "")
            if not drive_id:
                raise ValueError(
                    f"Carta sin ID de Drive en <{section_tag}> "
                    f"(slots: '{slots_text.strip() or 'desconocidos'}', "
                    f"nombre: '{name or 'sin nombre'}')"
                )
            cards.append(CardImage(drive_id=drive_id, name=name, slots=_parse_slots(slots_text)))
        return cards

    cardback_id = root.findtext("cardback", "").strip()
    if not cardback_id:
        raise ValueError("El XML no tiene un <cardback> definido o está vacío.")

    order = CardOrder(
        quantity=quantity,
        fronts=parse_cards("fronts"),
        backs=parse_cards("backs"),
        cardback_id=cardback_id,
    )
    _log.debug(
        "Parsed %s: %d fronts, %d backs, quantity=%d",
        Path(xml_path).name, len(order.fronts), len(order.backs), quantity,
    )
    return order
