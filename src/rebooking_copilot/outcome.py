"""Outcome enums shared by the decision engine and the reasoner."""

from enum import StrEnum


class Action(StrEnum):
    REBOOK = "REBOOK"
    DO_NOT_REBOOK = "DO_NOT_REBOOK"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class Confidence(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


BANDS = (Confidence.HIGH, Confidence.MEDIUM, Confidence.LOW)  # index = number of one-band drops


def lowest(*levels: Confidence) -> Confidence:
    return max(levels, key=BANDS.index)
