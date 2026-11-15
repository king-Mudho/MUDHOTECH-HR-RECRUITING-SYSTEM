"""Versioned matching thresholds (docs/05 §8.3: "stored in engine_config with version").

Defaults until the Phase 10 calibration on the labelled set; evaluations record ``version`` so a
changed threshold produces a new evaluation version, never a silent rescoring.
"""

from __future__ import annotations

from pydantic import Field

from ai_engine.contracts import Contract


class EngineConfig(Contract):
    version: str = "2026.11.1"
    semantic_skill_threshold: float = Field(default=0.78, ge=0, le=1)
    role_relevance_threshold: float = Field(default=0.6, ge=0, le=1)
    # EC-DOC-24: a skill only listed scores lower than one used in a role or project
    skill_listed_only: int = 50
    skill_mentioned: int = 75  # profile, achievements, certifications, education
    skill_used: int = 100  # experience, attachment, projects
    relation_cap: int = 75  # inferred via implies/narrower
    related_score: int = 25  # "related" skills are weak, indirect evidence
    semantic_cap: int = 50


DEFAULT_CONFIG = EngineConfig()
