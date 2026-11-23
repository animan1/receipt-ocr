"""Engine-independent observations in the coordinate space of the prepared image."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Box:
    left: float
    top: float
    right: float
    bottom: float

    @classmethod
    def from_pixels(
        cls, left: float, top: float, right: float, bottom: float, width: int, height: int
    ) -> "Box":
        return cls(
            max(0.0, min(1.0, left / width)),
            max(0.0, min(1.0, top / height)),
            max(0.0, min(1.0, right / width)),
            max(0.0, min(1.0, bottom / height)),
        )


@dataclass(frozen=True)
class Span:
    id: str
    text: str
    box: Box | None = None
    confidence: float | None = None


@dataclass(frozen=True)
class Observation:
    """Text spans in the order supplied by the engine, where available."""

    spans: tuple[Span, ...]
    page: int = 1
