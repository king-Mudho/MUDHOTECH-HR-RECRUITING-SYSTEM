"""Pydantic contracts exchanged between the AI engine stages and the Django adapters (docs/05).

Every stage is a pure function over these models. They are frozen and strict (unknown fields are
rejected) so a stage can never silently invent or drop data. Invariants enforced here:

* every extracted claim carries a non-empty source snippet (<= 300 chars) and a location
  (document page + character offsets, or a questionnaire response) - principle 2;
* a claim's ``data`` determines its type (discriminated union), so type and payload never disagree;
* claims excluded for protected or untrusted content (``excluded_reason``) can never enter
  ``CandidateEvidence``, the only input matching accepts - principles 7 and 8;
* dates are validated (month 1-12, ranges not reversed) with an explicit precision.

Criterion and evaluation contracts are added in Phase 07.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .versioning import ENGINE_VERSION, input_hash

SNIPPET_MAX = 300


class Contract(BaseModel):
    """Immutable, strict base for every engine contract."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)


# ------------------------------------------------------------------------- vocabularies
class EvidenceStatus(StrEnum):
    """Criterion-level evidence (principle 2 evidence-first, principle 3 missing != negative)."""

    FOUND = "found"
    MISSING = "missing"
    INFERRED = "inferred"
    CONFLICTING = "conflicting"
    HUMAN_VERIFIED = "human_verified"


class ClaimEvidence(StrEnum):
    """How a single claim was obtained."""

    EXPLICIT = "explicit"  # stated directly in the document
    INFERRED = "inferred"  # derived, e.g. a skill implied by a project's technology list


class ExtractionMethod(StrEnum):
    RULE = "rule"
    SECTION = "section"
    NER = "ner"
    TAXONOMY = "taxonomy"
    EMBEDDING = "embedding"
    OCR = "ocr"
    LLM = "llm"
    QUESTIONNAIRE = "questionnaire"
    HUMAN = "human"  # candidate/HR correction (ClaimCorrection)


class ExtractionStatus(StrEnum):
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"


class Flag(StrEnum):
    """Document/extraction flags (docs/05 §2-4, §6.1, §9). Flags inform humans; they never score."""

    ENCRYPTED_PDF = "encrypted_pdf"
    CORRUPT = "corrupt"
    TOO_MANY_PAGES = "too_many_pages"
    UNSUPPORTED_FORMAT = "unsupported_format"
    OCR_USED = "ocr_used"
    LOW_OCR_CONFIDENCE = "low_ocr_confidence"
    OCR_UNAVAILABLE = "ocr_unavailable"  # OCR needed but no engine installed
    GARBLED_TEXT = "garbled_text"
    HIDDEN_TEXT = "hidden_text"
    INJECTION_SUSPECTED = "injection_suspected"
    LANGUAGE_UNSUPPORTED = "language_unsupported"
    POSSIBLY_NOT_CV = "possibly_not_cv"
    DATE_ANOMALY = "date_anomaly"
    TIMEOUT = "timeout"


class ExcludedReason(StrEnum):
    """Why a claim is kept for audit but never used for evaluation."""

    PROTECTED_ATTRIBUTE = "protected_attribute"  # DOB/age, ID, gender, religion, health, ...
    HIDDEN_TEXT = "hidden_text"
    INJECTION = "injection"
    PERSONAL_SECTION = "personal_section"
    REFERENCES_SECTION = "references_section"


class SectionKind(StrEnum):
    PROFILE = "profile"
    EXPERIENCE = "experience"
    ATTACHMENT = "attachment"  # Industrial Attachment / internship sections
    EDUCATION = "education"
    SKILLS = "skills"
    CERTIFICATIONS = "certifications"
    PROJECTS = "projects"
    LANGUAGES = "languages"
    ACHIEVEMENTS = "achievements"
    PERSONAL = "personal"  # excluded from evaluation
    REFERENCES = "references"  # excluded from evaluation
    OTHER = "other"


EXCLUDED_SECTIONS = frozenset({SectionKind.PERSONAL, SectionKind.REFERENCES})


class EmploymentKind(StrEnum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    INTERNSHIP = "internship"
    ATTACHMENT = "attachment"
    VOLUNTEER = "volunteer"
    SELF_EMPLOYED = "self_employed"
    UNKNOWN = "unknown"


class DatePrecision(StrEnum):
    MONTH = "month"
    YEAR = "year"


class BlockKind(StrEnum):
    TEXT = "text"
    TABLE = "table"
    HEADER = "header"
    FOOTER = "footer"
    TEXTBOX = "textbox"
    OCR = "ocr"


# ------------------------------------------------------------------------- document text
class BBox(Contract):
    x0: float
    y0: float
    x1: float
    y1: float


class Block(Contract):
    """A run of text with its position and the typography sectioning needs."""

    text: str
    kind: BlockKind = BlockKind.TEXT
    bbox: BBox | None = None
    font_size: float | None = Field(default=None, ge=0)
    bold: bool = False
    hidden: bool = False  # white/tiny/off-page text: stored, flagged, never evaluated
    char_start: int = Field(default=0, ge=0)  # offset within the page text


class Page(Contract):
    number: int = Field(ge=1)
    text: str = ""
    width: float | None = Field(default=None, gt=0)
    height: float | None = Field(default=None, gt=0)
    blocks: tuple[Block, ...] = ()
    image_only: bool = False
    ocr: bool = False
    ocr_confidence: float | None = Field(default=None, ge=0, le=100)


class DocumentText(Contract):
    """Normalised text of one document, page by page (docs/05 §3)."""

    document_id: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mime: str
    parser_used: str
    pages: tuple[Page, ...] = ()
    language: str | None = None
    quality_score: float | None = Field(default=None, ge=0, le=1)
    flags: frozenset[Flag] = frozenset()

    @field_validator("pages")
    @classmethod
    def _pages_numbered_in_order(cls, pages: tuple[Page, ...]) -> tuple[Page, ...]:
        if [p.number for p in pages] != list(range(1, len(pages) + 1)):
            raise ValueError("pages must be numbered 1..n in order")
        return pages

    @property
    def char_count(self) -> int:
        return sum(len(p.text) for p in self.pages)

    def page(self, number: int) -> Page:
        return self.pages[number - 1]


class Section(Contract):
    kind: SectionKind
    heading: str = ""
    page: int = Field(ge=1)
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)

    @model_validator(mode="after")
    def _ordered(self) -> Section:
        if self.char_end < self.char_start:
            raise ValueError("char_end must be >= char_start")
        return self

    @property
    def evaluable(self) -> bool:
        return self.kind not in EXCLUDED_SECTIONS


# ------------------------------------------------------------------------------- dates
class PartialDate(Contract):
    year: int = Field(ge=1900, le=2100)
    month: int | None = Field(default=None, ge=1, le=12)
    precision: DatePrecision = DatePrecision.MONTH

    @model_validator(mode="after")
    def _precision_matches(self) -> PartialDate:
        if self.precision == DatePrecision.MONTH and self.month is None:
            raise ValueError("month precision needs a month")
        return self

    def ordinal(self, *, end: bool = False) -> int:
        """Month index; a year-only start counts from January, a year-only end to December."""
        month = self.month or (12 if end else 1)
        return self.year * 12 + month - 1


class DateRange(Contract):
    start: PartialDate | None = None
    end: PartialDate | None = None
    is_current: bool = False

    @model_validator(mode="after")
    def _not_reversed(self) -> DateRange:
        if self.is_current and self.end is not None:
            raise ValueError("a current role has no end date")
        if self.start and self.end and self.end.ordinal(end=True) < self.start.ordinal():
            raise ValueError("end is before start")
        return self


# --------------------------------------------------------------------------- claim data
class ExperienceData(Contract):
    type: Literal["experience"] = "experience"
    title: str = ""
    employer: str = ""
    location: str = ""
    dates: DateRange = DateRange()
    employment_kind: EmploymentKind = EmploymentKind.UNKNOWN
    responsibilities: tuple[str, ...] = ()
    title_normalised: str = ""  # normalisation/titles.py
    seniority: str | None = None  # intern | trainee | junior | mid | senior | lead | head


class EducationData(Contract):
    type: Literal["education"] = "education"
    qualification_text: str
    institution: str = ""
    level: str | None = None  # qualification level code (taxonomy), None = not mapped yet
    field: str = ""
    dates: DateRange = DateRange()
    grade: str = ""
    foreign: bool = False
    needs_verification: bool = False  # e.g. unrecognised or foreign qualification


class CertificationData(Contract):
    type: Literal["certification"] = "certification"
    name: str
    body: str = ""
    issued: PartialDate | None = None
    expires: PartialDate | None = None
    licence_class: str = ""  # e.g. driver's licence class 4


class SkillData(Contract):
    type: Literal["skill"] = "skill"
    raw: str
    skill_id: str | None = None  # taxonomy id when matched
    canonical: str | None = None
    years: float | None = Field(default=None, ge=0, le=60)


class LanguageData(Contract):
    type: Literal["language"] = "language"
    language: str
    level: str = ""


class ProjectData(Contract):
    type: Literal["project"] = "project"
    title: str
    description: str = ""
    technologies: tuple[str, ...] = ()


class ContactData(Contract):
    """Contact details: used for duplicate detection only, never for evaluation."""

    type: Literal["contact"] = "contact"
    email: str = ""
    phone: str = ""
    city: str = ""


class SummaryData(Contract):
    type: Literal["summary"] = "summary"
    text: str


class ProtectedData(Contract):
    """A detected protected attribute, kept only so audits can prove it was excluded."""

    type: Literal["protected"] = "protected"
    attribute: str  # date_of_birth | national_id | gender | marital_status | religion | ...


ClaimData = Annotated[
    ExperienceData
    | EducationData
    | CertificationData
    | SkillData
    | LanguageData
    | ProjectData
    | ContactData
    | SummaryData
    | ProtectedData,
    Field(discriminator="type"),
]
NOT_EVALUATED_TYPES = frozenset({"contact", "protected"})


# ------------------------------------------------------------------------------- claims
class ClaimSource(Contract):
    """Where a claim came from. A snippet is always required (no claim without evidence)."""

    snippet: str = Field(min_length=1, max_length=SNIPPET_MAX)
    document_id: str | None = None
    page: int | None = Field(default=None, ge=1)
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    question_response_id: str | None = None

    @model_validator(mode="after")
    def _located(self) -> ClaimSource:
        in_document = self.document_id is not None and self.page is not None
        if not in_document and self.question_response_id is None:
            raise ValueError("a source needs a document page or a questionnaire response")
        if (self.char_start is None) != (self.char_end is None):
            raise ValueError("char_start and char_end go together")
        if (
            self.char_start is not None
            and self.char_end is not None
            and self.char_end < self.char_start
        ):
            raise ValueError("char_end must be >= char_start")
        return self


class ExtractedClaim(Contract):
    data: ClaimData
    source: ClaimSource
    method: ExtractionMethod
    confidence: float = Field(ge=0, le=1)
    evidence: ClaimEvidence = ClaimEvidence.EXPLICIT
    section: SectionKind | None = None
    excluded_reason: ExcludedReason | None = None

    @model_validator(mode="after")
    def _exclusions_are_consistent(self) -> ExtractedClaim:
        if self.data.type == "protected" and self.excluded_reason is None:
            raise ValueError("protected attributes must carry excluded_reason")
        if self.section in EXCLUDED_SECTIONS and self.excluded_reason is None:
            raise ValueError("claims from personal/references sections must be excluded")
        return self

    @property
    def claim_type(self) -> str:
        return self.data.type

    @property
    def evaluable(self) -> bool:
        return self.excluded_reason is None and self.data.type not in NOT_EVALUATED_TYPES


class ExtractionResult(Contract):
    """Output of the extraction pipeline for one document (persisted as an ExtractionRun)."""

    engine_version: str = ENGINE_VERSION
    status: ExtractionStatus
    document: DocumentText | None = None  # None when the document could not be read at all
    sections: tuple[Section, ...] = ()
    claims: tuple[ExtractedClaim, ...] = ()
    flags: frozenset[Flag] = frozenset()
    error_code: str | None = None
    timings_ms: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _status_consistent(self) -> ExtractionResult:
        if self.status == ExtractionStatus.FAILED and not self.error_code:
            raise ValueError("a failed extraction needs an error_code")
        if self.status != ExtractionStatus.FAILED and self.document is None:
            raise ValueError("a successful extraction needs the document text")
        return self

    def evaluable_claims(self) -> tuple[ExtractedClaim, ...]:
        return tuple(c for c in self.claims if c.evaluable)

    def excluded_claims(self) -> tuple[ExtractedClaim, ...]:
        return tuple(c for c in self.claims if not c.evaluable)


class CandidateEvidence(Contract):
    """Everything matching may look at for one application - and nothing else (docs/05 §1).

    Built only from evaluable claims: protected, hidden, injected, contact and personal/references
    content is rejected here, so it cannot reach matching or any LLM prompt.
    """

    application_id: str
    engine_version: str = ENGINE_VERSION
    document_ids: tuple[str, ...] = ()
    claims: tuple[ExtractedClaim, ...] = ()
    total_experience_months: int = Field(default=0, ge=0)
    experience_months_by_kind: dict[EmploymentKind, int] = Field(default_factory=dict)
    flags: frozenset[Flag] = frozenset()

    @field_validator("claims")
    @classmethod
    def _only_evaluable(cls, claims: tuple[ExtractedClaim, ...]) -> tuple[ExtractedClaim, ...]:
        bad = [c for c in claims if not c.evaluable]
        if bad:
            raise ValueError(
                f"{len(bad)} excluded or non-evaluable claim(s) cannot be evaluation input"
            )
        return claims

    @classmethod
    def from_results(
        cls,
        application_id: str,
        results: list[ExtractionResult],
        *,
        total_experience_months: int = 0,
        experience_months_by_kind: dict[EmploymentKind, int] | None = None,
    ) -> CandidateEvidence:
        """Collect the evaluable claims of every document of an application."""
        return cls(
            application_id=application_id,
            document_ids=tuple(r.document.document_id for r in results if r.document),
            claims=tuple(c for r in results for c in r.evaluable_claims()),
            total_experience_months=total_experience_months,
            experience_months_by_kind=experience_months_by_kind or {},
            flags=frozenset(f for r in results for f in r.flags),
        )

    def of_type(self, claim_type: str) -> tuple[ExtractedClaim, ...]:
        return tuple(c for c in self.claims if c.claim_type == claim_type)

    def input_hash(self) -> str:
        """Deterministic hash of the evaluation input (principle 5: re-evaluate = new version)."""
        return input_hash(self.model_dump(mode="json"))


class SourceRef(Contract):
    """Where a criterion result's evidence came from (Phase 07 explanations)."""

    document_id: str | None = None
    page: int | None = None
    snippet: str | None = None
    question_response_id: str | None = None
