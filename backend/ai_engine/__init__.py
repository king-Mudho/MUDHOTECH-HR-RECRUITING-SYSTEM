"""MHRS AI engine - framework-free (no Django imports).

Pipeline: extraction -> normalisation -> matching -> evaluation -> explanations (docs/05).
Django adapters live in ``apps.resumes`` and ``apps.screening``.
"""

from .versioning import ENGINE_VERSION

__all__ = ["ENGINE_VERSION"]
