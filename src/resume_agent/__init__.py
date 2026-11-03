"""resume-parser-agent：简历 → 结构化 JSON 的抽取 Agent。"""

__version__ = "0.1.0"

from .pipeline import ParseOutcome, ResumePipeline  # noqa: F401
from .schema import CandidateProfile, ExtractionResult  # noqa: F401