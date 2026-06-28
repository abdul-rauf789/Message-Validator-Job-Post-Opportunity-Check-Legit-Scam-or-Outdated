# Job Post Validator

A fully rule-based pipeline that takes raw WhatsApp messages and classifies them through a 3-stage funnel — **no API key, no internet connection required** (link checking is optional).

Built to handle high-volume datasets (4,000+ messages) that would exhaust any free-tier LLM quota in seconds.

---

## What It Does

```
Raw WhatsApp Message
        │
        ▼
┌─────────────────────┐
│  Stage 1: Job Post? │  ──── NO ──→  Label: NOT-JOB  (exit)
└─────────────────────┘
        │ YES
        ▼
┌──────────────────────────┐
│  Stage 2: Real Opport.?  │  ── NO ──→  Label: NOT-REAL  (exit)
└──────────────────────────┘
        │ YES
        ▼
┌──────────────────┐
│  Link Check      │  (optional — checks if URL resolves)
└──────────────────┘
        │
        ▼
┌──────────────────────────────────┐
│  Stage 3: legit / scam / outdated│
└──────────────────────────────────┘
```

---

## Quick Start

### 1. Install dependencies

No extra packages needed beyond the Python standard library.  
`data_loader.py` and `sample_messages.py` are included in the project.

```bash
# Python 3.10+ required
python --version
```

### 2. Run on your CSV dataset

```powershell
python main.py
```

### 3. Limit to first N messages (fast test)

```powershell
python main.py --limit 50
```

### 4. Skip link checking (much faster — processes 1000s of messages in seconds)

```powershell
python main.py --no-links
```

### 5. Run on built-in synthetic samples (no CSV needed)

```powershell
python main.py --synthetic
```

### 6. Process a single message by ID

```powershell
python main.py --id CSV_42
```

### 7. Save results

```powershell
# JSON output
python main.py --out results.json

# CSV output
python main.py --csv-out results.csv

# Both at once
python main.py --limit 200 --out results.json --csv-out results.csv
```

### 8. Run tests

```powershell
python tests.py -v
```

---

## Project Structure

```
Message_Validator/
├── main.py              ← Entry point / CLI runner
├── pipeline.py          ← Core rule-based engine (3 stages)
├── data_loader.py       ← CSV + image loader
├── sample_messages.py   ← Built-in synthetic test messages
├── tests.py             ← 46 unit tests (all passing)
├── DECISIONS.md         ← Design decisions write-up
├── messages_export.csv  ← Your WhatsApp export data
└── _data/               ← Message images (optional)
```

---

## How Each Stage Works

### Stage 1 — Is it a job post?

Uses **30+ regex patterns** covering English and Urdu (romanized + native script).

**Positive signals detected:**
- Hiring verbs: `we are hiring`, `now hiring`, `looking for candidates`
- Application instructions: `send your CV`, `apply now`, `walk-in interview`
- Salary mentions: `PKR 80,000`, `salary:`, `market competitive`
- Role titles with context: `hiring manager / engineer / nurse / teacher`
- Urdu keywords: `نوکری`, `ملازمت`, `بھرتی`
- Job board URLs from sites like `jobz.pk`, `governmentjob.pk`

**Hard exclusions (never a job post):**
| Pattern | Example |
|---|---|
| Scholarship / fellowship | "King Fahd Scholarship 2026 (Fully Funded)" |
| Exam / schedule update | "FPSC exams postponed — new schedule soon" |
| Free course / certification | "Google released 10 AI courses for FREE" |
| Person seeking a job | "I am looking for a job in marketing" |
| Vague reference | "You can check their job section on LinkedIn" |
| Stub / one-liner | "AR executive" |
| Scholarship domains | URLs from `opportunitiescorners.com`, `fullyscholarships.com` |

---

### Stage 2 — Is it a real opportunity?

Needs **≥ 2 of 4 signals** to pass:

| Signal | Examples |
|---|---|
| **Role clarity** | "Position: Sales Manager", "Hiring: RCM Specialist" |
| **Org identity** | Company name, email domain, trusted job board URL |
| **Location** | "Lahore", "Gulberg", "Remote", "I-9/3 Islamabad" |
| **Apply path** | Email, phone, WhatsApp number, link, "send CV" |

**Always rejected:**
- Unfilled templates: `[COMPANY NAME]`, `[ROLE]`
- Rumours: "I heard Google is hiring"
- Vague calls: "DM us anytime if interested"

Trusted job board URLs (jobz.pk, rozee.pk, linkedin.com, governmentjob.pk, etc.) count as both **org identity** and **apply path** simultaneously.

---

### Stage 3 — Legit / Scam / Outdated?

#### Outdated (checked first)
| Signal | Example |
|---|---|
| Position filled | "Position has been filled", "vacancy is closed" |
| Past tense | "We were hiring for a marketing executive" |
| Past year only | Post mentions 2019/2020/2023 with no current year |
| Broken link + old year | 404 response + "Jobs 2020" in text |

#### Scam (requires ≥ 2 signals to avoid false positives)
| Signal | Example |
|---|---|
| Upfront fee | "Registration fee: PKR 2,000 required" |
| Implausible pay | "Earn PKR 50,000 daily" |
| NIC / bank details | "Send CNIC copy to apply" |
| No experience needed | "No skills required, anyone can apply" |
| Urgency + pressure | "Limited seats — act now! Offer expires tonight" |
| Identity spoofing | "GOOGLE is hiring work from home agents" |
| Vague overseas promise | "Easy overseas job — guaranteed 100%" |

**False positive protection:**
- A single `URGENT` keyword → **not** scam (common in legitimate hospitality/billing ads)
- High salary in tech/finance → **not** scam
- WhatsApp-based applications at small clinics → **not** scam
- Gmail contact address → **not** scam
- Poor grammar → **not** scam
- Trusted job board domain → scam threshold raised to ≥ 3 signals

#### Legit
Everything that doesn't trip scam or outdated thresholds. Confidence is boosted by:
- Trusted domain (jobz.pk, linkedin.com, governmentjob.pk, etc.)
- Resolving link (HTTP 200)
- Presence of email address, phone number, or named company

---

## Output Labels

| Label | Meaning |
|---|---|
| `NOT-JOB` | Not a job post at all |
| `NOT-REAL` | Mentions a job but not an actionable opportunity |
| `LEGIT` | Real job post, no red flags |
| `SCAM` | Real job post with ≥ 2 scam signals |
| `OUTDATED` | Real job post but position is closed / expired |

---

## CLI Reference

```
usage: python main.py [options]

options:
  --limit N       Process only first N messages
  --id ID         Process a single message by its CSV id
  --out FILE      Save results to JSON file
  --csv-out FILE  Save results to CSV file
  --synthetic     Use built-in sample messages (no CSV needed)
  --no-links      Skip HTTP link resolution (much faster)
```

---

## Running Tests

```powershell
python tests.py        # summary output
python tests.py -v     # verbose (shows each test name)
```

**46 tests** across 5 classes:

| Test Class | What It Covers |
|---|---|
| `TestStage1IsJobPost` | 11 tests — scholarships, stubs, exam updates, person-seeking, legit detection |
| `TestStage2IsRealOpportunity` | 7 tests — vague posts, rumours, placeholder templates, real postings |
| `TestStage3Classify` | 8 tests — scam signals, sloppy-but-legit edge case, outdated detection |
| `TestFullPipeline` | 15 tests — end-to-end funnel, broken links, batch processing, serialization |
| `TestUtilities` | 5 tests — URL extraction, link checker |

**Edge cases explicitly tested:**
- A job-mentioning message that isn't a real opportunity (`MSG_NOT_REAL_VAGUE`)
- A scam-flavored posting that's actually legit (`MSG_SCAM_SLOPPY_BUT_LEGIT` — uses "URGENT" but has real org/location/email)
- A broken link (`MSG_BROKEN_LINK` — 404 response + "2020" in text → `outdated`)

---

## Performance

Because there are no API calls, the pipeline is extremely fast:

| Mode | Speed |
|---|---|
| `--no-links` | ~5,000 messages/second |
| With link checking | Limited by network latency (~1–5 sec/message with a link) |

For 4,500 messages with links, use `--no-links` first to get classifications instantly, then run a targeted link check on only the Stage 3 results.

---

## Design Decisions

See [`DECISIONS.md`](DECISIONS.md) for the full write-up covering:
1. How Stage 1 and Stage 2 are separated
2. What distinguishes scam from sloppy-but-legit
3. Why link content is not parsed or trusted

---

## Supported Languages

- **English** — full support
- **Urdu (native script)** — keyword matching for `نوکری`, `ملازمت`, `بھرتی`, `ملازمین`
- **Urdu (romanized)** — `naukri` and common mixed-script patterns
- **Mixed English/Urdu** — handled naturally since both pattern sets run on every message
