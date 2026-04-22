from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class ReviewCell:
    section: str
    row: int
    col: int
    confidence: float
    reason: str


@dataclass
class DraftDocument:
    version: int
    sourceType: str
    shaftCount: int
    treadleCount: int
    threading: list[int]
    tieUp: list[list[bool]]
    treadling: list[int]
    drawdown: list[list[int]]
    warpColors: list[str]
    weftColors: list[str]
    parseConfidence: float
    warnings: list[str] = field(default_factory=list)
    lowConfidenceCells: list[ReviewCell] = field(default_factory=list)
    title: str | None = None
    sourceLabel: str | None = None
    renderSettings: dict | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class YarnAsset:
    id: str
    label: str
    status: str
    sourceFilename: str
    sourceUrl: str
    diffuseFilename: str | None = None
    diffuseUrl: str | None = None
    alphaFilename: str | None = None
    alphaUrl: str | None = None
    preprocessedFilename: str | None = None
    preprocessedUrl: str | None = None
    preprocessMeta: dict = field(default_factory=dict)
    alphaMeta: dict = field(default_factory=dict)
    error: str | None = None
    createdAt: str | None = None
    updatedAt: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ColorBinding:
    scope: str
    colorHex: str
    yarnAssetId: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FabricProject:
    version: int
    draft: dict
    yarnAssets: list[dict]
    colorBindings: list[ColorBinding]

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["colorBindings"] = [binding.to_dict() for binding in self.colorBindings]
        return payload
