"""Semantic catalog loader and governance validator."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class DimensionSpec(BaseModel):
    """Governed dimension definition."""

    name: str
    type: Literal["time", "categorical"]
    sql_expr: str
    description: str
    granularities: list[str] = Field(default_factory=list)
    allowed_values: list[str] = Field(default_factory=list)


class MetricSpec(BaseModel):
    """Governed metric definition."""

    name: str
    label: str
    type: Literal["simple", "ratio"]
    format: Literal["currency_brl", "percentage", "bps", "integer"]
    description: str
    sql_expr: str
    synonyms: list[str] = Field(default_factory=list)


class SemanticCatalog(BaseModel):
    """Complete governed semantic catalog loaded from contracts/semantic_catalog.yaml."""

    version: str
    semantic_layer_engine: str
    source_mart: str
    owner: str
    dimensions: dict[str, DimensionSpec]
    metrics: dict[str, MetricSpec]

    @classmethod
    def from_yaml(cls, path: Path) -> SemanticCatalog:
        """Load and validate the semantic catalog from YAML."""
        with path.open("r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)

        dimensions = {
            name: DimensionSpec(name=name, **cfg) for name, cfg in raw.get("dimensions", {}).items()
        }
        metrics = {
            name: MetricSpec(name=name, **cfg) for name, cfg in raw.get("metrics", {}).items()
        }
        return cls(
            version=raw["version"],
            semantic_layer_engine=raw["semantic_layer_engine"],
            source_mart=raw["source_mart"],
            owner=raw["owner"],
            dimensions=dimensions,
            metrics=metrics,
        )

    def to_llm_context(self) -> str:
        """Render a concise catalog specification for LLM function-calling prompts."""
        metric_lines = [
            f"- {m.name} ({m.label}, {m.type}): {m.description}" for m in self.metrics.values()
        ]
        dim_lines = []
        for d in self.dimensions.values():
            extra = (
                f"allowed={d.allowed_values}"
                if d.allowed_values
                else f"granularities={d.granularities}"
            )
            dim_lines.append(f"- {d.name} ({d.type}, {extra}): {d.description}")
        return (
            "GOVERNED METRICS:\n"
            + "\n".join(metric_lines)
            + "\n\nGOVERNED DIMENSIONS:\n"
            + "\n".join(dim_lines)
        )
