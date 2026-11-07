"""Fake perception for testing integration. Not computer vision, and not a result.

There are no real images: a stub "image" carries its true category, and the error rates
below are made up. Logs from this model are marked ``stub`` and say nothing about how
well real perception works. Ammar's module replaces both classes.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .contract import PerceptionResult

IMAGES_PER_CATEGORY = 5
N_WITHHELD = 3


def _unit_hash(*parts: object) -> float:
    digest = hashlib.sha256("|".join(map(str, parts)).encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


@dataclass(frozen=True)
class StubImage:
    ref: str
    true_category: str


class StubImagePool:
    """Opaque refs for each category. The rarest categories are withheld from the model."""

    def __init__(self, n_categories: int, n_withheld: int = N_WITHHELD) -> None:
        self.categories = tuple(f"category_{k:02d}" for k in range(n_categories))
        self.withheld = self.categories[-n_withheld:] if n_withheld else ()
        self._images: dict[str, StubImage] = {}
        self._refs: dict[str, tuple[str, ...]] = {}
        for category in self.categories:
            refs = []
            for index in range(IMAGES_PER_CATEGORY):
                digest = hashlib.sha256(f"{category}|{index}".encode()).hexdigest()[:16]
                ref = f"stub://{digest}"
                self._images[ref] = StubImage(ref, category)
                refs.append(ref)
            self._refs[category] = tuple(refs)

    def images_for(self, category: str) -> tuple[str, ...]:
        return self._refs[category]

    def load(self, ref: str) -> StubImage:
        return self._images[ref]


class StubPerception:
    """Makes deterministic, seeded mistakes, so downstream code must cope with errors."""

    name = "stub"

    def __init__(
        self,
        pool: StubImagePool,
        seed: int = 0,
        confusion_rate: float = 0.15,
        false_alert_rate: float = 0.05,
        missed_unknown_rate: float = 0.2,
    ) -> None:
        self._familiar = tuple(c for c in pool.categories if c not in pool.withheld)
        self._withheld = set(pool.withheld)
        self._seed = seed
        self._confusion_rate = confusion_rate
        self._false_alert_rate = false_alert_rate
        self._missed_unknown_rate = missed_unknown_rate

    def predict(self, image: StubImage) -> PerceptionResult:
        draw = _unit_hash(self._seed, "outcome", image.ref)
        wrong_label = self._familiar[
            int(_unit_hash(self._seed, "label", image.ref) * len(self._familiar))
        ]
        if image.true_category in self._withheld:
            unknown = draw >= self._missed_unknown_rate
            label = None if unknown else wrong_label
        elif draw < self._false_alert_rate:
            unknown, label = True, None
        else:
            unknown = False
            confused = draw < self._false_alert_rate + self._confusion_rate
            label = wrong_label if confused else image.true_category

        spread = _unit_hash(self._seed, "score", image.ref)
        novelty = 0.6 + 0.4 * spread if unknown else 0.4 * spread
        return PerceptionResult(label, 1.0 - novelty, novelty, unknown, image.ref)
