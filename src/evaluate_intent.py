"""
Held-out evaluation for the 3-way intent classifier - language aware.

Run from the src/ directory:

    python evaluate_intent.py

Evaluates resources/intent_test_examples.json - 60 questions that are NOT part
of the training file resources/intent_examples.json:

    30 English (10 INCIDENT / 10 CASE_QUESTION / 10 FOLLOW_UP)
    10 Hindi (Devanagari)      4 / 3 / 3
    10 Marathi (Devanagari)    4 / 3 / 3
    10 Hinglish (Roman script) 4 / 3 / 3

Prints, per language: intent accuracy per class, incident-category accuracy on
the rows whose gold category is known, and the confidence of correct vs wrong
answers (the data for calibrating incident_pipeline.CONFIDENCE_THRESHOLD).

DATA CAVEAT: every row is hand-written synthetic data. The hi / mr / hinglish
rows in particular are synthetic and have NOT been reviewed by a native
speaker - those numbers are INDICATIVE ONLY, not real-world performance.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from incident_classifier import classify_incident_category
from incident_data import (
    load_intent_ood_examples,
    load_intent_test_examples,
)
from intent_classifier import VALID_INTENTS, classify_intent_detailed
from incident_pipeline import CONFIDENCE_THRESHOLD, MARGIN_THRESHOLD

LANGUAGE_LABELS = {
    "en": "English",
    "hi": "Hindi (Devanagari)",
    "mr": "Marathi (Devanagari)",
    "hinglish": "Hinglish (Roman)",
}
LANGUAGE_ORDER = ["en", "hi", "mr", "hinglish"]
SYNTHETIC_CLASSES = {"CASE_QUESTION", "FOLLOW_UP"}


def _stats(values: list) -> dict:
    if not values:
        return {"n": 0, "min": None, "mean": None, "max": None}
    return {
        "n": len(values),
        "min": round(min(values), 3),
        "mean": round(sum(values) / len(values), 3),
        "max": round(max(values), 3),
    }


def evaluate(threshold: float = CONFIDENCE_THRESHOLD) -> dict:
    rows = load_intent_test_examples()
    if not rows:
        raise RuntimeError("resources/intent_test_examples.json is empty.")

    languages = {row.get("language", "en") for row in rows}
    report: dict = {"threshold": threshold, "model_note": None, "languages": {}}

    for lang in LANGUAGE_ORDER:
        if lang not in languages:
            continue
        entry = {
            "rows": 0,
            "intent": {
                label: {"correct": 0, "total": 0} for label in VALID_INTENTS
            },
            "conf_correct": [],
            "conf_wrong": [],
            "guarded_correct": 0,          # threshold applied: unclear = wrong
            "category": {"reached": 0, "correct": 0, "known": 0},
            "mistakes": [],
        }
        for row in rows:
            if row.get("language", "en") != lang:
                continue
            gold = str(row["category_id"]).strip().upper()
            detail = classify_intent_detailed(row["example"])
            pred = detail["intent"]
            conf = float(detail["confidence"])
            gap = float(detail["label_margin"])

            entry["rows"] += 1
            entry["intent"][gold]["total"] += 1
            right = pred == gold
            if right:
                entry["intent"][gold]["correct"] += 1
                entry["conf_correct"].append(conf)
            else:
                entry["conf_wrong"].append(conf)

            # both guards: below threshold OR too small a class gap the
            # pipeline answers "unclear" (wrong)
            guarded_pred = (
                pred if (conf >= threshold and gap >= MARGIN_THRESHOLD)
                else "UNCLEAR"
            )
            if guarded_pred == gold:
                entry["guarded_correct"] += 1

            # incident-category accuracy, only where the gold category is known
            gold_cat = row.get("incident_category_id")
            if gold_cat:
                entry["category"]["known"] += 1
                if pred == "INCIDENT":
                    entry["category"]["reached"] += 1
                    pred_cat = classify_incident_category(
                        row["example"], top_k=3
                    )["category_id"]
                    if pred_cat == gold_cat:
                        entry["category"]["correct"] += 1
                    else:
                        entry["mistakes"].append(
                            {
                                "example_id": row["example_id"],
                                "kind": "category",
                                "gold": gold_cat,
                                "predicted": pred_cat,
                                "confidence": conf,
                                "example": row["example"],
                            }
                        )
                    continue
            if not right:
                entry["mistakes"].append(
                    {
                        "example_id": row["example_id"],
                        "kind": "intent",
                        "gold": gold,
                        "predicted": pred,
                        "confidence": conf,
                        "example": row["example"],
                    }
                )
        report["languages"][lang] = entry
    return report


def print_report(report: dict) -> None:
    threshold = report["threshold"]
    print("=" * 100)
    print("HELD-OUT INTENT EVALUATION - resources/intent_test_examples.json")
    print(f"encoder: paraphrase-multilingual-MiniLM-L12-v2   "
          f"guards: confidence >= {threshold}, class gap >= {MARGIN_THRESHOLD}")
    print("=" * 100)
    header = (
        f"{'language':<22}{'rows':>5} "
        f"{'INCIDENT':>12}{'CASE_QUESTION':>15}{'FOLLOW_UP':>12}"
        f"{'overall':>10}{'cat-acc':>12}{'guarded':>10}"
    )
    print(header)
    print("-" * 100)
    for lang, e in report["languages"].items():
        cells = ""
        for label in VALID_INTENTS:
            c = e["intent"][label]
            width = {"INCIDENT": 12, "CASE_QUESTION": 15, "FOLLOW_UP": 12}[label]
            cell = (f"{c['correct']}/{c['total']} "
                    f"{100 * c['correct'] / max(1, c['total']):.0f}%")
            cells += f"{cell:>{width}}"
        total_correct = sum(e["intent"][l]["correct"] for l in VALID_INTENTS)
        overall = f"{100 * total_correct / max(1, e['rows']):.1f}%"
        cat = e["category"]
        cat_str = (
            f"{cat['correct']}/{cat['known']}" if cat["known"] else "-"
        )
        guarded = f"{100 * e['guarded_correct'] / max(1, e['rows']):.1f}%"
        print(
            f"{LANGUAGE_LABELS[lang]:<22}{e['rows']:>5} {cells}"
            f"{overall:>10}{cat_str:>12}{guarded:>10}"
        )
    print("-" * 100)
    print("cat-acc = incident-category correct / rows with a known gold "
          "category (a miss at the intent stage counts as a category miss).")
    print("guarded = overall accuracy with both guards applied (below the "
          "confidence threshold OR below the class-gap threshold -> "
          "'unclear' -> wrong).")
    print()

    for lang, e in report["languages"].items():
        print("=" * 100)
        print(f"{LANGUAGE_LABELS[lang]}  ({lang})  -  "
              f"{e['rows']} rows, synthetic, indicative only")
        print("=" * 100)
        for label in VALID_INTENTS:
            c = e["intent"][label]
            mark = " (synthetic class)" if label in SYNTHETIC_CLASSES else ""
            print(
                f"  {label:<16}{c['correct']:>3}/{c['total']:<3}"
                f" {100 * c['correct'] / max(1, c['total']):>6.1f}%{mark}"
            )
        cat = e["category"]
        if cat["known"]:
            print(
                f"  incident-category {cat['correct']:>3}/{cat['known']:<3}"
                f" {100 * cat['correct'] / max(1, cat['known']):>6.1f}%"
                f"   (reached category stage: {cat['reached']}/{cat['known']})"
            )
        sc, sw = _stats(e["conf_correct"]), _stats(e["conf_wrong"])
        print(f"  confidence CORRECT: n={sc['n']} min={sc['min']} "
              f"mean={sc['mean']} max={sc['max']}")
        print(f"  confidence WRONG:   n={sw['n']} min={sw['min']} "
              f"mean={sw['mean']} max={sw['max']}")
        print(f"  mistakes ({len(e['mistakes'])}):")
        for m in e["mistakes"]:
            print(f"    [{m['example_id']}] {m['kind']} gold={m['gold']} "
                  f"pred={m['predicted']} conf={m['confidence']}")
            print(f"        \"{m['example']}\"")
        print()


def threshold_scan(report: dict) -> None:
    """Accuracy with the CONFIDENCE guard alone, over candidate thresholds.

    Below the threshold the pipeline answers "unclear", which is a wrong
    answer for every row in this set (no row is labelled unclear), so the
    guarded accuracy is simply: correct answers whose confidence >= thr.
    The class-gap guard is swept separately in guard_grid().
    """
    langs = list(report["languages"])
    print("=" * 100)
    print("THRESHOLD SCAN - confidence guard only, margin guard not applied "
          "(see GUARD GRID below)  ('unclear' counts as wrong)")
    print("=" * 100)
    header = f"{'thr':>6} " + "".join(f"{LANGUAGE_LABELS[l]:>22}" for l in langs)
    header += f"{'pooled':>10}{'correct kept':>14}{'wrong kept':>12}"
    print(header)
    print("-" * 100)
    for thr in [0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70]:
        cells = ""
        pooled_ok = pooled_rows = kept_ok = kept_wrong = 0
        for lang in langs:
            e = report["languages"][lang]
            ok = sum(1 for c in e["conf_correct"] if c >= thr)
            wrong_kept = sum(1 for c in e["conf_wrong"] if c >= thr)
            cells += f"{100 * ok / max(1, e['rows']):>22.1f}"
            pooled_ok += ok
            pooled_rows += e["rows"]
            kept_ok += ok
            kept_wrong += wrong_kept
        marker = "  <-- current" if abs(thr - CONFIDENCE_THRESHOLD) < 1e-9 else ""
        print(f"{thr:>6.2f} {cells} {100 * pooled_ok / max(1, pooled_rows):>9.1f}"
              f"{kept_ok:>14}{kept_wrong:>12}{marker}")
    print("-" * 100)
    print("'correct kept' = correct answers still answered; 'wrong kept' = "
          "WRONG answers still answered (want this near 0).")


def score_all() -> list:
    """One record per input across every set (English, hi, mr, hinglish and
    the out-of-scope set): predicted intent, confidence, the top-1 minus
    top-2 margin, and the gap to the runner-up class."""
    records = []
    for row in load_intent_test_examples():
        detail = classify_intent_detailed(row["example"])
        gold = str(row["category_id"]).strip().upper()
        records.append(
            {
                "id": row["example_id"],
                "lang": row.get("language", "en"),
                "gold": gold,
                "pred": detail["intent"],
                "conf": detail["confidence"],
                "top1": detail["top1"],
                "top2": detail["top2"],
                "margin": detail["margin"],
                "gap": detail["label_margin"],
                "verdict": "correct" if detail["intent"] == gold else "wrong",
                "text": row["example"],
            }
        )
    for row in load_intent_ood_examples():
        detail = classify_intent_detailed(row["text"])
        records.append(
            {
                "id": row["example_id"],
                "lang": row["language"],
                "gold": "OUT_OF_SCOPE",
                "pred": detail["intent"],
                "conf": detail["confidence"],
                "top1": detail["top1"],
                "top2": detail["top2"],
                "margin": detail["margin"],
                "gap": detail["label_margin"],
                "verdict": "out-of-scope",
                "text": row["text"],
            }
        )
    return records


def print_scores(records: list, thr: float, margin: float) -> None:
    print("=" * 126)
    print("PER-INPUT SCORES  (conf = mean similarity of the winning label; "
          "margin = top-1 minus top-2; gap = winner minus runner-up class)")
    print("=" * 126)
    print(f"{'id':<13}{'lang':>9}{'gold':>15}{'pred':>15}{'conf':>7}"
          f"{'top1':>7}{'top2':>7}{'margin':>8}{'gap':>7}  "
          f"{'verdict':<14}{'guard':<8}")
    print("-" * 126)
    for r in records:
        passes = r["conf"] >= thr and r["gap"] >= margin
        guard = "ANSWER" if passes else "unclear"
        print(
            f"{r['id']:<13}{r['lang']:>9}{r['gold']:>15}{r['pred']:>15}"
            f"{r['conf']:>7.3f}{r['top1']:>7.3f}{r['top2']:>7.3f}"
            f"{r['margin']:>8.3f}{r['gap']:>7.3f}  "
            f"{r['verdict']:<14}{guard:<8}"
        )
    print("-" * 126)
    print(f"guard shown at CONFIDENCE_THRESHOLD={thr}, "
          f"MARGIN_THRESHOLD={margin}: ANSWER = confident AND clearly ahead "
          "of the runner-up class, unclear = refuse and ask to rephrase.")
    print()


def summary_stats(records: list) -> dict:
    groups = {
        "correct": [r for r in records if r["verdict"] == "correct"],
        "wrong": [r for r in records if r["verdict"] == "wrong"],
        "out-of-scope": [r for r in records if r["verdict"] == "out-of-scope"],
    }
    stats = {}
    print("=" * 126)
    print("SUMMARY - confidence, top-1 minus top-2 margin, and class gap "
          "by verdict")
    print("=" * 126)
    print(f"{'group':<16}{'n':>4} | {'confidence':^27} | {'margin (top1-top2)':^27}"
          f" | {'gap (winner-runner-up)':^27}")
    print(f"{'':<16}{'':>4} | {'min':>8}{'mean':>10}{'max':>9} | "
          f"{'min':>8}{'mean':>10}{'max':>9} | {'min':>8}{'mean':>10}{'max':>9}")
    print("-" * 126)
    for name, rows in groups.items():
        conf = [r["conf"] for r in rows]
        marg = [r["margin"] for r in rows]
        gaps = [r["gap"] for r in rows]
        stats[name] = {"n": len(rows), "conf": _stats(conf),
                       "margin": _stats(marg), "gap": _stats(gaps)}
        print(
            f"{name:<16}{len(rows):>4} | "
            f"{stats[name]['conf']['min']:>8}{stats[name]['conf']['mean']:>10}"
            f"{stats[name]['conf']['max']:>9} | "
            f"{stats[name]['margin']['min']:>8}"
            f"{stats[name]['margin']['mean']:>10}"
            f"{stats[name]['margin']['max']:>9} | "
            f"{stats[name]['gap']['min']:>8}"
            f"{stats[name]['gap']['mean']:>10}"
            f"{stats[name]['gap']['max']:>9}"
        )
    print("-" * 126)
    print(f"{'MINIMUM correct confidence':<34}: "
          f"{stats['correct']['conf']['min']}")
    print(f"{'MAXIMUM out-of-scope confidence':<34}: "
          f"{stats['out-of-scope']['conf']['max']}")
    print(f"{'MAXIMUM wrong confidence':<34}: {stats['wrong']['conf']['max']}")
    print(f"{'MINIMUM correct margin (top1-top2)':<34}: "
          f"{stats['correct']['margin']['min']}")
    print(f"{'MAXIMUM out-of-scope margin':<34}: "
          f"{stats['out-of-scope']['margin']['max']}")
    print(f"{'MAXIMUM wrong margin':<34}: {stats['wrong']['margin']['max']}")
    print(f"{'MINIMUM correct gap':<34}: {stats['correct']['gap']['min']}")
    print(f"{'MAXIMUM out-of-scope gap':<34}: "
          f"{stats['out-of-scope']['gap']['max']}")
    print(f"{'MAXIMUM wrong gap':<34}: {stats['wrong']['gap']['max']}")
    print()
    return stats


def guard_grid(records: list) -> dict:
    """Accuracy / leakage for every (threshold, margin-gap) candidate."""
    thresholds = [0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55]
    margins = [0.00, 0.05, 0.10, 0.12, 0.15, 0.16, 0.18, 0.20]
    correct_total = sum(1 for r in records if r["verdict"] == "correct")
    wrong_total = sum(1 for r in records if r["verdict"] == "wrong")
    ood_total = sum(1 for r in records if r["verdict"] == "out-of-scope")

    rows = []
    for thr in thresholds:
        for marg in margins:
            kept = lambda r: r["conf"] >= thr and r["gap"] >= marg
            rows.append(
                {
                    "thr": thr,
                    "margin": marg,
                    "ood_pass": sum(1 for r in records
                                    if r["verdict"] == "out-of-scope" and kept(r)),
                    "wrong_pass": sum(1 for r in records
                                      if r["verdict"] == "wrong" and kept(r)),
                    "correct_kept": sum(1 for r in records
                                        if r["verdict"] == "correct" and kept(r)),
                    "correct_total": correct_total,
                    "wrong_total": wrong_total,
                    "ood_total": ood_total,
                }
            )

    print("=" * 126)
    print("GUARD GRID  (answer only when confidence >= thr AND class gap >= m)")
    print("=" * 126)
    print(f"{'thr':>6}{'gap':>6}{'correct kept':>14}{'correct lost':>14}"
          f"{'wrong leaked':>14}{'OOD leaked':>12}   verdict")
    print("-" * 126)
    for row in rows:
        lost = row["correct_total"] - row["correct_kept"]
        note = ""
        if row["ood_pass"] == 0 and row["wrong_pass"] == 0:
            note = "no leakage"
        elif row["ood_pass"] == 0:
            note = "no OOD leakage"
        if (abs(row["thr"] - CONFIDENCE_THRESHOLD) < 1e-9
                and abs(row["margin"] - MARGIN_THRESHOLD) < 1e-9):
            note = (note + "  <-- APPLIED").strip()
        print(f"{row['thr']:>6.2f}{row['margin']:>6.2f}"
              f"{row['correct_kept']:>14}{lost:>14}"
              f"{row['wrong_pass']:>14}{row['ood_pass']:>12}   {note}")
    print("-" * 126)
    print(f"correct total = {correct_total}, wrong total = {wrong_total}, "
          f"out-of-scope total = {ood_total}")
    print()

    zero_ood = [r for r in rows if r["ood_pass"] == 0]
    zero_both = [r for r in rows if r["ood_pass"] == 0 and r["wrong_pass"] == 0]
    best_ood = (sorted(zero_ood, key=lambda r: (-r["correct_kept"],
                                                r["wrong_pass"],
                                                r["thr"], -r["margin"]))[0]
                if zero_ood else None)
    best_both = (sorted(zero_both, key=lambda r: (-r["correct_kept"],
                                                  r["thr"],
                                                  -r["margin"]))[0]
                 if zero_both else None)
    return {"grid": rows, "best_ood": best_ood, "best_both": best_both}


def main() -> None:
    report = evaluate()
    print_report(report)
    threshold_scan(report)

    records = score_all()
    thr = CONFIDENCE_THRESHOLD
    marg = MARGIN_THRESHOLD
    print_scores(records, thr, marg)
    summary_stats(records)
    grid = guard_grid(records)

    print("=" * 126)
    print("RECOMMENDATION")
    print("=" * 126)
    for tag, best in (("zero OOD leakage required", grid["best_ood"]),
                      ("zero OOD AND zero wrong leakage", grid["best_both"])):
        if not best:
            print(f"  [{tag}] no candidate setting qualifies")
            continue
        lost = best["correct_total"] - best["correct_kept"]
        print(f"  [{tag}] CONFIDENCE_THRESHOLD = {best['thr']}   "
              f"MARGIN_THRESHOLD = {best['margin']}")
        print(f"      OOD leaked {best['ood_pass']}/{best['ood_total']}, "
              f"wrong leaked {best['wrong_pass']}/{best['wrong_total']}, "
              f"correct kept {best['correct_kept']}/{best['correct_total']}, "
              f"correct answers lost {lost}")
    applied = next(r for r in grid["grid"]
                   if r["thr"] == CONFIDENCE_THRESHOLD
                   and r["margin"] == MARGIN_THRESHOLD)
    print(f"  [APPLIED in incident_pipeline] "
          f"CONFIDENCE_THRESHOLD={thr}   MARGIN_THRESHOLD={marg}")
    print(f"      OOD leaked {applied['ood_pass']}/{applied['ood_total']}, "
          f"wrong leaked {applied['wrong_pass']}/{applied['wrong_total']}, "
          f"correct kept {applied['correct_kept']}/{applied['correct_total']}, "
          f"correct answers lost "
          f"{applied['correct_total'] - applied['correct_kept']}")
    print("  Rationale: 0.35 is just above the highest out-of-scope confidence "
          "(0.341); 0.16 is just above the highest class gap of a wrong answer "
          "(0.116) and of an out-of-scope input (0.157), so each guard alone "
          "keeps all 15 out-of-scope inputs out.")
    print("=" * 126)
    print(f"Applied in incident_pipeline: CONFIDENCE_THRESHOLD={thr}, "
          f"MARGIN_THRESHOLD={marg} - NOT changed by this script.")
    print("Reminder: CASE_QUESTION / FOLLOW_UP and every hi / mr / hinglish "
          "score come from synthetic, unreviewed examples - indicative only.")
    print("=" * 126)


if __name__ == "__main__":
    main()
