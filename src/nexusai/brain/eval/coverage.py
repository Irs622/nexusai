"""CoverageAnalyzer for analyzing ScenarioCorpus dataset quality and coverage ratios."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from nexusai.brain.eval.scenario import ScenarioCorpus


@dataclass(frozen=True)
class CoverageReport:
    """Quality report analyzing category, difficulty, and tag coverage across a ScenarioCorpus.

    Attributes:
        corpus_name: Dataset corpus name string.
        total_scenarios: Total number of scenarios in corpus.
        category_coverage: Ratio map per category (TOOL, RECOVERY, PLANNING, REFLECTION, COMPACTION).
        difficulty_coverage: Ratio map per difficulty (EASY, MEDIUM, HARD).
        tag_distribution: Frequency map of scenario tags.
        source_distribution: Frequency map of scenario origins (SYNTHETIC, REAL_LOG, GITHUB_ISSUE).
        is_balanced: Boolean flag indicating equal category balance across corpus.
    """

    corpus_name: str
    total_scenarios: int = 0
    category_coverage: dict[str, float] = field(default_factory=dict)
    difficulty_coverage: dict[str, float] = field(default_factory=dict)
    tag_distribution: dict[str, int] = field(default_factory=dict)
    source_distribution: dict[str, int] = field(default_factory=dict)
    is_balanced: bool = False

    def save_json(self, file_path: Path | str) -> None:
        """Save CoverageReport to JSON file."""
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")


class CoverageAnalyzer:
    """Analyzes a ScenarioCorpus dataset for category taxonomy coverage and dataset balance."""

    def analyze(self, corpus: ScenarioCorpus) -> CoverageReport:
        """Analyze ScenarioCorpus dataset coverage and balance."""
        total = len(corpus.scenarios)
        if total == 0:
            return CoverageReport(corpus_name=corpus.corpus_name)

        categories: dict[str, int] = {}
        difficulties: dict[str, int] = {}
        tags: dict[str, int] = {}
        sources: dict[str, int] = {"SYNTHETIC": 0, "REAL_LOG": 0, "GITHUB_ISSUE": 0}

        for sc in corpus.scenarios:
            cat = sc.category or "GENERAL"
            categories[cat] = categories.get(cat, 0) + 1

            diff = sc.difficulty or "MEDIUM"
            difficulties[diff] = difficulties.get(diff, 0) + 1

            for tag in sc.tags:
                tags[tag] = tags.get(tag, 0) + 1

            # Determine source tag or fallback to SYNTHETIC
            src_found = False
            for t in sc.tags:
                if t.upper() in sources:
                    sources[t.upper()] += 1
                    src_found = True
                    break
            if not src_found:
                sources["SYNTHETIC"] += 1

        cat_ratios = {cat: round(count / total, 4) for cat, count in categories.items()}
        diff_ratios = {diff: round(count / total, 4) for diff, count in difficulties.items()}

        # Dataset is balanced if all 5 core categories have >= 15% representation
        expected_cats = {"TOOL", "RECOVERY", "PLANNING", "REFLECTION", "COMPACTION"}
        is_balanced = expected_cats.issubset(set(categories.keys())) and all(
            r >= 0.15 for cat, r in cat_ratios.items() if cat in expected_cats
        )

        return CoverageReport(
            corpus_name=corpus.corpus_name,
            total_scenarios=total,
            category_coverage=cat_ratios,
            difficulty_coverage=diff_ratios,
            tag_distribution=tags,
            source_distribution=sources,
            is_balanced=is_balanced,
        )
