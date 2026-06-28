# Design Decisions — Message Validator

## 1. Separating "not a job post" from "job post that isn't a real opportunity"

**Stage 1** filters intent: does this message *offer* a role? Scholarship posts, exam updates, course announcements, and person-seeking-job messages are hard-excluded via dedicated NOT_JOB_PATTERNS before JOB_SIGNALS are scored. Stub messages (single line with no actionable content) are also rejected. Only messages with ≥1 positive hiring signal *and* no overriding non-job context advance.

**Stage 2** filters actionability: can a candidate actually apply? A real opportunity needs ≥2 of four signals: (role clarity, org identity, location, apply path). This separates "We're hiring! DM anytime" (0–1 signals) from a proper posting with a role title, company name, Lahore address, and an email.

## 2. Scam vs. legitimate-but-sloppy

Scam classification requires **≥2 co-occurring red-flag signals** from a named set: upfront fee, implausible pay, requesting NIC/bank details, "no experience needed," urgency+pressure, identity spoofing, or vague overseas promise. A single "URGENT" is common in legitimate hospitality/billing ads and does not trigger scam alone. Trusted job-board domains (jobz.pk, governmentjob.pk, rozee.pk, LinkedIn, etc.) raise the scam threshold to ≥3 signals.

**False positive risks:** high salaries in tech, WhatsApp-based application in SMEs, poor grammar in legitimate ads, informal posting style in small clinics. All of these are explicitly *not* counted as scam signals.

## 3. Trusting link content

Links are checked **only for HTTP resolution status** (HEAD request, then GET fallback). Page content is not parsed or trusted. An attacker could serve a professional-looking page for a scam job, so fetched content was deliberately excluded from classification logic. A broken link + past year in the text → *outdated*; a broken link with no date context → *legit* with reduced confidence. This avoids blind trust of adversarial page content while still using link liveness as a freshness signal.