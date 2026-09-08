"""Request specification and validation for PaperSmith runs."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path


class ConfigError(ValueError):
    pass


# Per-domain task profiles: drives the materials prompt, task.toml tags,
# config.yaml conference label, and the AGENTS.md domain line.
DOMAIN_PROFILES = {
    "biology": {
        "materials_domain": "biology",
        "tag": "biology",
        "conference": "arXiv q-bio",
        "experience": "Reconstructing a life-sciences research paper from a research overview, figures, tables and code under a fixed bibliography.",
        "agents_domain": "life-sciences",
        "arxiv_categories": ["q-bio.BM", "q-bio.QM", "q-bio.TO", "q-bio.MN", "q-bio.CB", "q-bio.GN"],
    },
    "physics": {
        "materials_domain": "physics",
        "tag": "physics",
        "conference": "arXiv physics",
        "experience": "Reconstructing a physics research paper from a research overview, figures, tables and code under a fixed bibliography.",
        "agents_domain": "physics",
        "arxiv_categories": [
            "cond-mat.mtrl-sci", "cond-mat.mes-hall", "cond-mat.str-el", "cond-mat.soft",
            "hep-th", "hep-ph", "gr-qc", "astro-ph.CO", "astro-ph.HE", "nucl-th",
            "quant-ph", "physics.optics", "physics.flu-dyn", "physics.plasm-ph", "physics.app-ph",
        ],
    },
}


def domain_profile(domain: str) -> dict:
    return DOMAIN_PROFILES.get(domain, DOMAIN_PROFILES["biology"])


@dataclass
class RequestSpec:
    request: str
    selection: str = "discovery"
    papers: list[str] = field(default_factory=list)
    count: int = 1
    output: Path | None = None
    model: str | None = None
    review_model: str | None = None
    backend: str | None = None
    source_roots: list[Path] = field(default_factory=list)
    domain: str = "biology"

    def validate(self) -> None:
        if self.selection not in ("fixed", "discovery"):
            raise ConfigError(f"unknown selection mode: {self.selection}")
        if not isinstance(self.count, int) or isinstance(self.count, bool) or self.count < 1:
            raise ConfigError("count must be a positive integer")
        if self.selection == "fixed" and not self.papers:
            raise ConfigError("fixed selection requires at least one --paper identifier")
        if self.selection == "discovery" and self.papers:
            raise ConfigError("--paper locks identity and therefore requires fixed selection")
        if self.output is not None:
            self.output = self.output.resolve()
        if self.domain not in DOMAIN_PROFILES:
            raise ConfigError(f"unknown domain: {self.domain} (expected one of {sorted(DOMAIN_PROFILES)})")
        resolved: list[Path] = []
        for root in self.source_roots:
            if not root.is_absolute():
                raise ConfigError(f"source root must be an absolute path: {root}")
            resolved.append(root.resolve())
        self.source_roots = resolved

    def to_dict(self) -> dict:
        data = asdict(self)
        data["output"] = str(self.output) if self.output is not None else None
        data["source_roots"] = [str(r) for r in self.source_roots]
        return data
