"""Aggregate comparable preparation measurements across the corpus."""

import json
from pathlib import Path
from statistics import median
from typing import cast

CaseScores = dict[str, dict[str, object] | None]
METRICS = {
    "colored_border_pct": "Colored crop border (%)",
    "long_side_p90_error_pct": "Worst long-side deviation (% of paper width)",
    "retained_background_pct": "Retained background (%)",
    "paper_lost_pct": "Paper lost (%)",
    "protected_regions_clipped": "Protected regions clipped",
    "median_abs_row_residual_degrees": "Median absolute row tilt (degrees)",
}


def metric_value(scores: dict[str, object] | None, key: str) -> float | None:
    value = scores.get(key) if scores is not None else None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, list):
        if key == "protected_regions_clipped":
            return float(len(value))
        return max(cast(list[float], value), default=None)
    return None


def write_summary(debug: Path, methods: list[str], cases: list[CaseScores], annotated: int) -> Path:
    baseline = methods[0]
    summary = []
    rows = []
    for key, label in METRICS.items():
        reference = [metric_value(case[baseline], key) for case in cases]
        for method in methods:
            values = [metric_value(case[method], key) for case in cases]
            measured = [value for value in values if value is not None]
            deltas = (
                [
                    value - base
                    for value, base in zip(values, reference, strict=True)
                    if value is not None and base is not None
                ]
                if method != baseline
                else []
            )
            center = round(median(measured), 2) if measured else None
            improved = sum(delta < 0 for delta in deltas)
            tied = sum(delta == 0 for delta in deltas)
            regressed = sum(delta > 0 for delta in deltas)
            summary.append(
                {
                    "metric": key,
                    "approach": method,
                    "cases_measured": len(measured),
                    "median": center,
                    "paired_cases": len(deltas),
                    "improved": improved,
                    "tied": tied,
                    "regressed": regressed,
                }
            )
            compare = f"{improved} / {tied} / {regressed}" if deltas else "—"
            shown = f"{center:.2f}" if center is not None else "—"
            rows.append(f"| {label} | {method} | {len(measured)} | {shown} | {compare} |")

    debug.mkdir(parents=True, exist_ok=True)
    (debug / "all-01-quality.json").write_text(
        json.dumps(
            {
                "image_cases": len(cases),
                "annotated_cases": annotated,
                "baseline": baseline,
                "metrics": summary,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    report = debug / "all-01-quality.md"
    report.write_text(
        "\n".join(
            [
                "# Image preparation quality",
                "",
                f"Compared {len(cases)} image fixtures, including {annotated} with independent annotations.",
                f"The baseline is `{baseline}`. Lower values are better for each metric.",
                "",
                "Border color and long-side deviation can be measured without annotations. The other rows",
                "use labeled cases. Counts vary when an approach lacks the geometry for a metric.",
                "Wins, ties, and losses use only cases measured by both the approach and the baseline.",
                "",
                "| Metric | Approach | Cases measured | Median | Improved / tied / regressed |",
                "| --- | --- | ---: | ---: | ---: |",
                *rows,
                "",
            ]
        ),
        encoding="utf-8",
    )
    return report
