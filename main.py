"""
Main Runner — Message Validator Pipeline (Rule-Based)
------------------------------------------------------
Usage:
    # Run on the real dataset (CSV)
    python main.py

    # Limit to first N messages (for quick testing)
    python main.py --limit 50

    # Run single message by CSV id
    python main.py --id CSV_42

    # Output results to JSON file
    python main.py --limit 100 --out results.json

    # Save results as CSV
    python main.py --out results.json --csv-out results.csv

    # Run on built-in synthetic samples (no CSV needed)
    python main.py --synthetic

    # Skip link checking (much faster)
    python main.py --no-links
"""

import os
import sys
import json
import argparse
import csv
from pathlib import Path

from pipeline import MessageValidatorPipeline, ValidationResult

# ── Built-in synthetic samples (used with --synthetic flag) ────
SAMPLE_MESSAGES = [
    {"id": "SYN_01", "text": (
        "📢 We Are Hiring – Fresh Graduates Welcome!\n"
        "Position: Medical Billing Support\n"
        "Company: MediMax Solutions\n"
        "Location: Commercial Market, Rawalpindi\n"
        "Working Hours: 5:00 PM – 2:00 AM, Mon–Fri\n"
        "Send CV to: hr@medimax.com.pk"
    )},
    {"id": "SYN_02", "text": (
        "King Fahd 🇸🇦 Scholarship 2026 for International Students (Fully Funded)\n"
        "Apply: https://opportunitiescorners.com/king-fahd-university-scholarship-2026/\n"
        "The Scholarship covers Airfare, Meals, Accommodation, Tuition."
    )},
    {"id": "SYN_03", "text": (
        "FPSC Exams Update\n"
        "Exams scheduled from 25 April to 06 May 2026 have been postponed.\n"
        "New Schedule to be announced soon."
    )},
    {"id": "SYN_04", "text": (
        "🚀 WORK FROM HOME OPPORTUNITY 🚀\n"
        "Earn PKR 50,000 daily! No experience needed.\n"
        "Limited seats — act now!\n"
        "Registration fee: PKR 2,000\n"
        "WhatsApp only: +923001234567"
    )},
    {"id": "SYN_05", "text": (
        "https://governmentjob.pk/jobs/ammunition-depot-pattoki-jobs-2026/\n\n"
        "Army Ammunition Depot Pattoki Jobs 2026 | Apply Offline"
    )},
    {"id": "SYN_06", "text": "We are hiring! DM us anytime if you're interested."},
    {"id": "SYN_07", "text": (
        "Position has been filled. Thank you for your interest.\n"
        "We were hiring for a marketing executive in Karachi."
    )},
    {"id": "SYN_08", "text": (
        "URGENT! Software Engineer needed.\n"
        "Company: TechCorp Pvt Ltd, Islamabad (Blue Area)\n"
        "Salary: PKR 150,000 – 200,000\n"
        "Experience: 3+ years Python/Django\n"
        "Email: careers@techcorp.com.pk"
    )},
]


def load_messages(csv_path: str, images_dir: str = "", deduplicate: bool = True,
                  limit: int = None) -> list[dict]:
    """Load messages from a WhatsApp export CSV."""
    import csv as _csv
    messages = []
    seen_texts = set()
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = _csv.DictReader(f)
        for i, row in enumerate(reader):
            if limit and len(messages) >= limit:
                break
            text = (row.get("text_content") or row.get("caption") or "").strip()
            if deduplicate:
                key = text[:200]
                if key in seen_texts:
                    continue
                seen_texts.add(key)
            img_path = None
            raw_img = row.get("image_path", "").strip()
            if raw_img and images_dir:
                import os
                candidates = [
                    os.path.join(images_dir, raw_img),
                    os.path.join(images_dir, "_data", raw_img),
                    os.path.join(images_dir, os.path.basename(raw_img)),
                ]
                for candidate in candidates:
                    if os.path.isfile(candidate):
                        img_path = candidate
                        break
            row_id = row.get("id", str(i + 1))
            messages.append({
                "id": f"CSV_{row_id}",
                "text": text,
                "image_path": img_path,
            })
    return messages


def print_dataset_stats(messages: list[dict]):
    total    = len(messages)
    has_img  = sum(1 for m in messages if m.get("image_path"))
    has_text = sum(1 for m in messages if m.get("text"))
    both     = sum(1 for m in messages if m.get("text") and m.get("image_path"))
    print(f"Dataset stats:")
    print(f"  Total unique messages : {total}")
    print(f"  Text + image          : {both}")
    print(f"  Text only             : {has_text - both}")
    print(f"  Image only            : {has_img - both}")
    print(f"  Has text              : {has_text}")
    print(f"  Has image             : {has_img}")


# ── Paths ──────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
CSV_PATH   = BASE_DIR / "messages_export.csv"
IMAGES_DIR = BASE_DIR / "_data" / "_data"


def print_banner():
    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║   WhatsApp Job Post Validator  (Rule-Based — No API)    ║")
    print("║  Stage1: Job? → Stage2: Real? → Stage3: Legit/Scam/Old ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()


def print_results_table(results: list[ValidationResult]):
    icons = {
        "legit":    "✅",
        "scam":     "⚠️ ",
        "outdated": "🕰️ ",
        "NOT-JOB":  "⛔",
        "NOT-REAL": "❓",
        "unknown":  "❔",
    }
    print()
    print(f"{'ID':<16} {'IMG'} {'STAGE':<10} {'RESULT':<10} {'CONF':<6} {'TIME'}")
    print("─" * 64)
    for r in results:
        lbl  = r.label()
        icon = icons.get(lbl, icons.get(r.classification or "", "❔"))
        img  = "🖼" if r.has_image else "  "
        conf = f"{r.confidence:.0%}" if r.confidence else "—"
        print(
            f"{r.message_id:<16} {img}  {r.stage_stopped_at:<10} "
            f"{lbl:<10} {conf:<6} {r.processing_time_ms:.0f}ms"
        )


def print_summary_stats(results: list[ValidationResult]):
    total    = len(results)
    if total == 0:
        print("No results.")
        return
    not_job  = sum(1 for r in results if not r.is_job_post)
    not_real = sum(1 for r in results if r.is_job_post and not r.is_real_opportunity)
    legit    = sum(1 for r in results if r.classification == "legit")
    scam     = sum(1 for r in results if r.classification == "scam")
    outdated = sum(1 for r in results if r.classification == "outdated")
    with_img = sum(1 for r in results if r.has_image)
    has_link = sum(1 for r in results if r.link_found)
    broken   = sum(1 for r in results if r.link_found and r.link_resolves is False)
    avg_ms   = sum(r.processing_time_ms for r in results) / total

    print()
    print("═" * 48)
    print("SUMMARY")
    print("═" * 48)
    print(f"  Total processed    : {total}")
    print(f"  With image         : {with_img}")
    print(f"  ─────────────────────────────")
    print(f"  ⛔ Not a job post  : {not_job:<5}  ({not_job/total:.0%})")
    print(f"  ❓ Not real opp.   : {not_real:<5}  ({not_real/total:.0%})")
    print(f"  ✅ Legit           : {legit:<5}  ({legit/total:.0%})")
    print(f"  ⚠️  Scam            : {scam:<5}  ({scam/total:.0%})")
    print(f"  🕰️  Outdated        : {outdated:<5}  ({outdated/total:.0%})")
    print(f"  ─────────────────────────────")
    print(f"  Links found        : {has_link}")
    print(f"  Broken links       : {broken}")
    print(f"  Avg time/message   : {avg_ms:.1f} ms")
    print()


def save_json(results: list[ValidationResult], path: str):
    with open(path, "w", encoding="utf-8") as f:
        json.dump([r.to_dict() for r in results], f, indent=2, ensure_ascii=False)
    print(f"✅ Results saved → {path}")


def save_csv(results: list[ValidationResult], path: str):
    fields = [
        "message_id", "has_image", "stage_stopped_at",
        "is_job_post", "is_real_opportunity", "classification",
        "confidence", "link_found", "link_resolves",
        "link_status_code", "reasoning", "processing_time_ms",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in results:
            row = r.to_dict()
            row["confidence"] = f"{r.confidence:.2f}" if r.confidence else ""
            w.writerow(row)
    print(f"✅ Results CSV saved → {path}")


def main():
    parser = argparse.ArgumentParser(description="WhatsApp Job Post Validator (Rule-Based)")
    parser.add_argument("--limit",      type=int, help="Max messages to process")
    parser.add_argument("--id",                   help="Process single message by id")
    parser.add_argument("--out",                  help="Save results to JSON file")
    parser.add_argument("--csv-out",              help="Save results to CSV file")
    parser.add_argument("--synthetic",  action="store_true", help="Use synthetic samples")
    parser.add_argument("--no-links",   action="store_true", help="Skip link resolution checks")
    args = parser.parse_args()

    print_banner()

    # Monkey-patch link checking if --no-links
    if args.no_links:
        import pipeline as _pl
        _pl.check_link = lambda url, timeout=8: (None, 0)
        print("⚡ Link checking disabled (--no-links)\n")

    pipeline = MessageValidatorPipeline()

    # ── Choose message source ───────────────────────────────────
    if args.synthetic:
        print("📋 Using synthetic sample messages\n")
        messages = [
            {"id": m["id"], "text": m["text"], "image_path": None}
            for m in SAMPLE_MESSAGES
        ]
    else:
        if not CSV_PATH.exists():
            print(f"❌ CSV not found at {CSV_PATH}")
            print("   Use --synthetic to run on built-in samples.")
            sys.exit(1)

        img_dir = str(IMAGES_DIR) if IMAGES_DIR.exists() else ""
        print(f"📂 Loading from : {CSV_PATH}")
        print(f"🖼  Images dir  : {img_dir or '(not found)'}")
        if not img_dir:
            print(f"   ⚠️  Folder not found — expected: {IMAGES_DIR}")

        messages = load_messages(
            csv_path=str(CSV_PATH),
            images_dir=img_dir or "/nonexistent",
            deduplicate=True,
            limit=args.limit,
        )
        print_dataset_stats(messages)

        # Show how many images were actually matched on disk
        img_count = sum(1 for m in messages if m.get("image_path"))
        if img_count:
            print(f"  ✅ Images matched on disk : {img_count}")
        else:
            print(f"  ⚠️  No images matched on disk (check _data folder location)")
        print()

        if args.id:
            messages = [m for m in messages if m["id"] == args.id]
            if not messages:
                print(f"❌ No message found with id: {args.id}")
                sys.exit(1)
        elif args.limit:
            messages = messages[: args.limit]

    print(f"Processing {len(messages)} messages...\n")
    results = pipeline.process_batch(messages, verbose=True)

    print_results_table(results)
    print_summary_stats(results)

    # Detailed view for stage-3 results (cap at 30)
    stage3 = [r for r in results if r.stage_stopped_at == "stage_3"]
    if stage3 and len(stage3) <= 30:
        print("═" * 58)
        print("DETAILED RESULTS (classified messages)")
        print("═" * 58)
        for r in stage3:
            print(r.full_summary())
            print()

    if args.out:
        save_json(results, args.out)
    if getattr(args, "csv_out", None):
        save_csv(results, args.csv_out)


if __name__ == "__main__":
    main()
