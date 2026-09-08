# harbor-canary GUID {{canary}}
"""Deterministic citation-key F1 scorer for the paper-reconstruction task.

Writes /logs/verifier/evaluation.json. The optional LLM per-section rubric is
omitted here; it requires a judge endpoint and is a later, optional addition.
The binary reward comes from test_state.py, not from this scorer.
"""
import json
import re
from pathlib import Path

OUTPUT = Path("/logs/verifier/evaluation.json")


def _cite_keys(tex_path: Path) -> set[str]:
    text = tex_path.read_text(encoding="utf-8", errors="replace")
    keys: set[str] = set()
    for match in re.finditer(
        r"\\(?:[A-Za-z]*cite[A-Za-z]*\*?)(?:\s*\[[^\]]*\]){0,2}\s*\{([^}]*)\}", text
    ):
        for key in match.group(1).split(","):
            key = key.strip()
            if key:
                keys.add(key)
    return keys


def evaluate_citation_f1(gt_path: Path, pred_path: Path) -> float:
    gt = _cite_keys(gt_path)
    pred = _cite_keys(pred_path)
    if not gt and not pred:
        return 1.0
    if not gt or not pred:
        return 0.0
    tp = len(gt & pred)
    precision = tp / len(pred)
    recall = tp / len(gt)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def main() -> None:
    pred = Path("/workspace/submission/main.tex")
    gt = Path("/tests/private/ground_truth.tex")
    citation = evaluate_citation_f1(gt, pred) if pred.is_file() and gt.is_file() else 0.0
    OUTPUT.write_text(
        json.dumps({"citation_f1": citation}, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"OFFICIAL_EVAL_WRITTEN {OUTPUT}")


if __name__ == "__main__":
    main()
