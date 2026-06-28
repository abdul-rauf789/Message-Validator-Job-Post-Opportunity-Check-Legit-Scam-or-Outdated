"""
Message Validator Pipeline  —  Rule-Based (No API Required)
-------------------------------------------------------------
Validates WhatsApp-style messages through a 3-stage funnel:

  Stage 1 → Is it a job post?
  Stage 2 → Is it a real opportunity?
  Stage 3 → Classify: legit / scam / outdated

Works fully offline using keyword matching, regex patterns, and
heuristic scoring.  Handles English + Urdu mixed messages.

Design decisions (see DECISIONS.md for full write-up):
  - Stage 1 uses positive JOB_SIGNALS minus NOT_JOB exclusions
  - Stage 2 requires ≥2 of: role, org, location, apply-path
  - Stage 3 scam needs ≥2 co-occurring red-flag signals
"""

import re
import time
import csv
import urllib.request
import urllib.error
from dataclasses import dataclass, asdict, field
from typing import Optional
from datetime import datetime, date
import os

# ─────────────────────────────────────────────────────────────────
# DATA STRUCTURES
# ─────────────────────────────────────────────────────────────────

@dataclass
class ValidationResult:
    message_id: str
    raw_text: str
    has_image: bool = False
    is_job_post: bool = False
    is_real_opportunity: bool = False
    classification: Optional[str] = None       # legit | scam | outdated
    confidence: Optional[float] = None
    link_found: Optional[str] = None
    link_resolves: Optional[bool] = None
    link_status_code: Optional[int] = None
    reasoning: Optional[str] = None
    stage_stopped_at: str = "stage_1"
    processing_time_ms: float = 0.0
    scam_signals: list = field(default_factory=list)
    outdated_signals: list = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("scam_signals", None)
        d.pop("outdated_signals", None)
        return d

    def label(self) -> str:
        if not self.is_job_post:
            return "NOT-JOB"
        if not self.is_real_opportunity:
            return "NOT-REAL"
        return (self.classification or "unknown").upper()

    def full_summary(self) -> str:
        lines = [
            f"━━━ [{self.message_id}] ━━━",
            f"  Is job post   : {self.is_job_post}",
        ]
        if self.is_job_post:
            lines.append(f"  Real opport.  : {self.is_real_opportunity}")
        if self.classification:
            lines.append(f"  Classification: {self.classification.upper()} (conf={self.confidence:.0%})")
        if self.link_found:
            lines.append(f"  Link          : {self.link_found}")
            lines.append(f"  Resolves      : {self.link_resolves} (HTTP {self.link_status_code})")
        if self.reasoning:
            lines.append(f"  Reasoning     : {self.reasoning}")
        if self.raw_text:
            lines.append(f"  Text preview  : {self.raw_text[:120].strip()!r}")
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────
# LINK UTILITIES
# ─────────────────────────────────────────────────────────────────

URL_RE = re.compile(r'https?://[^\s<>"\']+|www\.[^\s<>"\']+', re.IGNORECASE)


def extract_first_url(text: str) -> Optional[str]:
    m = URL_RE.search(text)
    if m:
        url = m.group(0).rstrip(".,;)")
        if not url.startswith("http"):
            url = "https://" + url
        return url
    return None


def check_link(url: str, timeout: int = 8) -> tuple[bool, int]:
    """Returns (resolves, http_status_code)."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
        )
    }
    try:
        req = urllib.request.Request(url, headers=headers, method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = resp.status
            return code < 400, code
    except urllib.error.HTTPError as e:
        return False, e.code
    except Exception:
        return False, 0


# ─────────────────────────────────────────────────────────────────
# RULE SETS
# ─────────────────────────────────────────────────────────────────

# ── Stage 1: Is it a job post? ───────────────────────────────────

# Strong job-offer signals (Urdu + English)
JOB_SIGNALS = [
    # English hiring verbs / nouns
    r"\bwe\s+are\s+hiring\b", r"\bnow\s+hiring\b", r"\bwe['']re\s+hiring\b",
    r"\bjob\s+(opening|vacancy|vacancies|opportunity|post|posting|offer|available)\b",
    r"\b(vacant|available)\s+position", r"\bvacant\s+post",
    r"\bapply\s+(now|online|here|below|at|by)\b",
    r"\bapplications?\s+(are\s+)?invited\b",
    r"\bwe\s+(need|require|seek|want)\b.{0,40}\b(candidates?|professionals?|staff|executive|manager|officer|engineer|analyst|specialist|coordinator|developer|designer|assistant|intern|teacher|doctor|nurse)\b",
    r"\b(looking\s+for|seeking)\b.{0,60}\b(candidate|professional|staff|hire|team\s+member|employee|applicant)\b",
    r"\bposition\s+(available|open|vacant|announced)\b",
    r"\b(join|joining)\s+(our\s+)?(team|company|organization|firm|group)\b",
    r"\bwalk[\s-]?in\s+interview",
    r"\bimmediately\s+(joiners?|required|needed|hiring)\b",
    r"\bsend\s+(your\s+)?(cv|resume|application)\b",
    r"\bshare\s+(your\s+)?(cv|resume)\b",
    r"\bcv\s+(share|send|submit|email|drop|forward)\b",
    r"\bwhatsapp\s+(your\s+)?(cv|resume)\b",
    r"\bjob\s+description\b", r"\bjd\b",
    r"\bsalary\s*[:–-]", r"\bpay\s*[:–-]", r"\bpackage\s*[:–-]",
    r"\bpkr\s*\d", r"\brs\s*\d{3,}",
    r"\b(full[\s-]?time|part[\s-]?time|remote|onsite|hybrid)\b.{0,80}\b(position|role|job|work|opportunity|hiring)\b",
    r"\bqualification\s*(required|needed|s?\s*:)",
    r"\bexperience\s+(required|needed|of|:)\s*\d",
    r"\b(male|female)\s+(candidates?|applicants?)\s+(are\s+)?(encouraged|welcome|can|may)\s+to\s+apply\b",
    r"\bhiring\b.{0,120}\b(position|role|staff|team|executive|manager|officer|engineer|specialist|coordinator|developer|intern|teacher|nurse|doctor)\b",
    # Urdu signals (romanized + native)
    r"\bnaukri\b", r"\bملازمت\b", r"\bنوکری\b",
    r"\bملازمین\b", r"\bبھرتی\b",
    r"\b(required|needed)\s+(staff|worker|employee|candidate|professional)\b",
    r"\binternship\s+(available|open|announced|offer)\b",
    r"\bjobs?\s+202[0-9]\b",            # "Jobs 2026" in title
    r"\bvacancies\s+202[0-9]\b",
    r"\bposts?\s+202[0-9]\b",
    r"\bjobs?\s+\|\s+apply\b",
    r"\bfreelance\s+(gig|project|work|opportunity|job)\b",
    r"\bcontract\s+(position|role|based|hiring)\b",
    r"\bvacant\s+positions?\s*:", r"\bpositions?\s+available\b",
    r"\b(apply|contact)\s+(via|through|on|at)\s+(whatsapp|email|linkedin|form)\b",
    r"\bdeadline\s*(:|to\s+apply|for\s+application)\b",
    r"\blast\s+date\s*(:|to|for)\b",
]

# Messages that mention jobs but are NOT job posts
NOT_JOB_PATTERNS = [
    r"\b(scholarship|fellowship|fellowship|grant|award|fully[\s-]?funded)\b",
    r"\bstudy\s+(abroad|in|at|for)\b",
    r"\b(bachelor|master|phd|mba|mphil|bs|ms)\s+(program|scholarship|degree|admission)\b",
    r"\b(university|college|institute)\s+(of|scholarship|admission|offer)\b",
    r"\btuition\s+fee\s+(waiver|covered|free|paid)\b",
    r"\b(course|training|workshop|bootcamp|seminar|webinar|conference|summit|program)\b.{0,60}\b(free|enroll|register|join|attend)\b",
    r"\bfpsc\s+(exam|test|schedule|update|postponed)\b",
    r"\b(exam|test|schedule|postponed|result)\s+update\b",
    r"\bi\s+(am|m)\s+(looking|searching|seeking)\s+(for\s+)?(a\s+)?(job|work|position|opportunity)\b",
    r"\bsomeone\s+looking\s+for\s+(a\s+)?job\b",
    r"\b(career|salary|tip|advice|guide|news|update|announcement)\b",
    r"\bcheck\s+(their|the|its)\s+job\s+section\b",
    r"\byou\s+can\s+(check|find|look)\b",
    r"\bi\s+heard\s+they\s*(are|'re)?\s*hiring\b",
    r"\bcultural\s+exchange\b",
    r"\bexchange\s+program\b",
    r"\bsummer\s+program\b",
    r"\bglobal\s+(youth|internship|program)\b.{0,80}\b(summit|conference|camp)\b",
    r"\bai\s+course",
    r"\b(free\s+certificate|certification\s+course|online\s+course)\b",
]

# Extra-short messages that are never real job posts on their own
STUB_PATTERNS = [
    r"^(ar\s+executive|sales\s+executive|hr\s+executive|accounts?\s+executive|"
    r"marketing\s+executive|business\s+executive|office\s+executive|"
    r"\+\d{10,13}|contact\s+no|dm\s+us|send\s+cv)\.?\s*$",
]

# ── Stage 2: Is it a real opportunity? ───────────────────────────

ROLE_SIGNALS = [
    r"\b(position|role|post|vacancy|opening|job\s+title|designation)\s*[:–\-]?\s*\w",
    r"\b(hiring|looking\s+for|seeking|require|need)\b.{0,80}\b(manager|officer|engineer|analyst|specialist|coordinator|developer|designer|assistant|intern|teacher|doctor|nurse|receptionist|executive|trainer|consultant|technician|operator|supervisor|director|head|lead|associate|advisor|representative|agent)\b",
    r"\bvacant\s+position",
    r"\bopen\s+(role|position|vacancy)",
]

ORG_SIGNALS = [
    r"\b(company|organization|firm|agency|hospital|clinic|school|college|university|institute|ngo|department|ministry|authority|corporation|group|pvt|ltd|llc|inc)\b",
    r"\b[A-Z][a-z]+\s+(Solutions|Technologies|Systems|Services|Group|Associates|Enterprises|Healthcare|Pharma|Consulting|International|Pakistan|Institute|Academy|Foundation|Limited)\b",
    r"\b(tcf|ptcl|nestle|unilever|hbl|uba|meezan|habib|mcb|allied|silk|telenor|jazz|zong|ufone|mobilink|airblue|pia|sui|wapda|ogdc|psmc|fauji|bahria|army|navy|air\s+force)\b",
    r"@[a-zA-Z0-9._-]+\.[a-zA-Z]{2,}",      # email domain implies org
    r"\bmedtransic\b|\bpitb\b|\bfuuast\b|\bhisd\b",
    r"\b[A-Z]{2,10}\b.{0,20}\b(pvt|ltd|limited|llc)\b",
]

LOCATION_SIGNALS = [
    r"\b(location|located|based|onsite|office)\s*[:–\-]?\s*(karachi|lahore|islamabad|rawalpindi|multan|peshawar|quetta|faisalabad|hyderabad|sialkot|gujranwala|dha|gulberg|i-\d|f-\d|g-\d|cantt|clifton|defence|johar|naz|soan|bahria|blue\s+area|satellite\s+town)\b",
    r"\b(karachi|lahore|islamabad|rawalpindi|multan|peshawar|quetta|faisalabad|hyderabad|sialkot|gujranwala|dubai|abu\s+dhabi|riyadh|jeddah|doha|muscat|uk|usa|uae|canada)\b",
    r"\b(remote|work\s+from\s+home|wfh|hybrid|on[\s-]?site)\b",
    r"\bsector\s+[a-zA-Z][\-/]\d",   # Islamabad sector codes like G-9/3
]

APPLY_SIGNALS = [
    r"\b(apply|email|whatsapp|contact|send|share|drop|forward|submit)\b.{0,60}\b(cv|resume|application|profile)\b",
    r"\bcv\b.{0,40}\b(send|share|email|drop|whatsapp|forward|submit)\b",
    r"\b(send|email|drop|forward)\b.{0,40}\b@[a-zA-Z0-9._-]+\.[a-zA-Z]{2,}\b",
    r"\b@[a-zA-Z0-9._-]+\.[a-zA-Z]{2,}\b",   # email present
    r"\bhttps?://[^\s]+\b",                    # any link = apply path candidate
    r"\bwhatsapp\b.{0,40}\b\d{10,13}\b",
    r"\b\+\d{10,13}\b",                        # phone number
    r"\bapply\s+(now|here|below|online|at|via|through)\b",
    r"\bwalk[\s-]?in\s+interview",
    r"\bdeadline\b|\blast\s+date\b",
]

# ── Stage 3: Scam signals ─────────────────────────────────────────

SCAM_SIGNALS = {
    "upfront_fee":     r"\b(registration\s+fee|processing\s+fee|security\s+deposit|pay\s+(first|before|to\s+join)|advance\s+payment|fee\s+(required|needed|must))\b",
    "implausible_pay": r"\b(earn|make|income|salary|daily|weekly)\b.{0,60}\b(\d{4,}\s*(per\s+(hour|day)|/hr|/day)|usd\s*\d{3,}|pkr\s*[1-9]\d{5,})\b",
    "nic_bank":        r"\b(nic|cnic|national\s+id|bank\s+(account|details)|account\s+number|passport\s+number)\s*(required|send|share|needed|copy)\b",
    "whatsapp_only":   r"\bwhatsapp\s+(only|me|us|him|her|them|at)\b.{0,40}\b\d{10,13}\b",
    "no_questions":    r"\b(no\s+experience\s+needed|no\s+skills?\s+(needed|required)|anyone\s+can\s+(apply|join)|no\s+qualification)\b",
    "too_good":        r"\b(earn\s+(easily|quickly|fast)|work\s+(from\s+home|anywhere).{0,40}\b(earn|income|salary)\b|part[\s-]?time.{0,60}\b(lakh|100k|50k|million|earn))\b",
    "urgency_pressure":r"\b(act\s+now|limited\s+seats?|spots?\s+(are\s+)?limited|hurry|don['']t\s+(miss|wait)|today\s+only|last\s+(chance|opportunity)|expire|closing\s+soon)\b",
    "identity_spoof":  r"\b(google|amazon|microsoft|apple|meta|facebook|un\b|united\s+nations|who\b|world\s+health)\b.{0,40}\b(hiring|job|recruit|intern)\b",
    "overseas_vague":  r"\b(abroad|overseas|foreign)\b.{0,80}\b(job|work|opportunity)\b.{0,80}\b(no\s+experience|easy|guaranteed|100%|sure)\b",
}

# ── Stage 3: Outdated signals ─────────────────────────────────────

PLACEHOLDER_RE = re.compile(
    r"\[\s*(company\s*name|role|city|position|department|your\s+name)\s*\]",
    re.IGNORECASE,
)

CURRENT_YEAR = datetime.now().year

OUTDATED_SIGNALS = {
    "past_year_in_text": None,   # Handled in code via _has_past_year()
    "deadline_passed":   r"\b(last\s+date|deadline|apply\s+by)\b.{0,40}\b\d{1,2}\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b",
    "position_filled":   r"\b(position\s+(has\s+been\s+)?(filled|closed)|no\s+longer\s+(hiring|accepting)|hiring\s+(is\s+)?closed|we\s+(have\s+)?filled|vacancy\s+(is\s+)?closed)\b",
    "past_tense_hiring": r"\bwe\s+were\s+hiring\b|\bwas\s+hiring\b|\bhad\s+been\s+hiring\b",
    "broken_link_old":   None,   # Handled in code: broken link + past date → outdated
}

# Trusted job board domains (helps confirm legit)
TRUSTED_DOMAINS = {
    "jobz.pk", "rozee.pk", "mustakbil.com", "bayt.com",
    "linkedin.com", "indeed.com", "glassdoor.com",
    "governmentjob.pk", "paperpk.com", "nts.org.pk",
    "fpsc.gov.pk", "ppsc.gop.pk", "bpsc.gop.pk", "kppsc.gov.pk",
    "pitb.gov.pk", "psca.gop.pk",
}

# Scholarship / non-job opportunity domains (Stage 1 exclusion boost)
SCHOLARSHIP_DOMAINS = {
    "opportunitiescorners.com", "fullyscholarships.com",
    "globalgleaning.com", "scholarshipscorner.website",
    "youthop.com", "abroadly.com",
}


# ─────────────────────────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """Lowercase, collapse whitespace, strip markdown/WhatsApp formatting."""
    text = re.sub(r"[*_`~]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.lower().strip()


def _matches_any(patterns: list, text: str) -> list[str]:
    """Return list of pattern strings that matched."""
    hits = []
    for p in patterns:
        if re.search(p, text, re.IGNORECASE):
            hits.append(p)
    return hits


def _score_signals(signal_dict: dict, text: str) -> dict[str, bool]:
    """Return which named signals fired."""
    result = {}
    for name, pattern in signal_dict.items():
        if pattern is None:
            result[name] = False
        else:
            result[name] = bool(re.search(pattern, text, re.IGNORECASE))
    return result


def _domain_of(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    m = re.search(r"https?://(?:www\.)?([^/?\s]+)", url, re.IGNORECASE)
    return m.group(1).lower() if m else None


def _has_past_year(text: str) -> bool:
    """True if text contains a year older than current year."""
    years = re.findall(r"\b(20\d{2})\b", text)
    return any(int(y) < CURRENT_YEAR for y in years)


def _has_future_or_current_year(text: str) -> bool:
    years = re.findall(r"\b(20\d{2})\b", text)
    return any(int(y) >= CURRENT_YEAR for y in years)


# ─────────────────────────────────────────────────────────────────
# STAGE IMPLEMENTATIONS
# ─────────────────────────────────────────────────────────────────

def stage1_is_job_post(text: str, url: Optional[str]) -> tuple[bool, float, str]:
    """
    Returns (is_job, confidence, reasoning).

    Decision logic:
    1. Hard-exclude scholarship/course/exam-update patterns.
    2. Hard-exclude stub messages (single line, no real content).
    3. Count positive JOB_SIGNALS hits — need ≥1 strong or ≥2 weak.
    4. Scholarship domain in URL → NOT a job post.
    """
    if not text or len(text.strip()) < 5:
        return False, 0.95, "Empty or near-empty message"

    norm = _normalize(text)

    # Hard exclude stubs
    for p in STUB_PATTERNS:
        if re.match(p, norm, re.IGNORECASE):
            return False, 0.85, "Message is too short/vague to be a job post"

    # Hard exclude scholarship/course/exam domains
    domain = _domain_of(url)
    if domain and domain in SCHOLARSHIP_DOMAINS:
        return False, 0.92, f"URL domain '{domain}' is a scholarship/opportunity site, not a job post"

    not_job_hits = _matches_any(NOT_JOB_PATTERNS, norm)
    job_hits = _matches_any(JOB_SIGNALS, norm)

    # If strong not-job signals fire and no job signals → not a job
    if len(not_job_hits) >= 2 and len(job_hits) == 0:
        return False, 0.88, f"Matches non-job patterns: {not_job_hits[:2]}"

    # Single not-job signal with no job signal
    if len(not_job_hits) >= 1 and len(job_hits) == 0:
        return False, 0.80, f"No job signal; matches non-job pattern"

    # Job signals present
    if len(job_hits) >= 2:
        conf = min(0.55 + 0.08 * len(job_hits), 0.97)
        return True, conf, f"Matched {len(job_hits)} job signals"

    if len(job_hits) == 1:
        # One job signal but also a strong non-job pattern → not a job
        if len(not_job_hits) >= 1:
            return False, 0.72, "Job signal present but overridden by non-job context"
        return True, 0.65, "Matched 1 job signal (low confidence)"

    return False, 0.78, "No job-post signals detected"


def stage2_is_real_opportunity(text: str, url: Optional[str]) -> tuple[bool, float, str]:
    """
    Returns (is_real, confidence, reasoning).

    A real opportunity needs ≥2 of: role clarity, org identity,
    location, apply path.  This filters vague forwarded rumours.
    """
    norm = _normalize(text)

    # Hard reject unfilled templates
    if PLACEHOLDER_RE.search(text):
        return False, 0.92, "Unfilled placeholder template — not a real posting"

    role_hits     = _matches_any(ROLE_SIGNALS, norm)
    org_hits      = _matches_any(ORG_SIGNALS, norm)
    location_hits = _matches_any(LOCATION_SIGNALS, norm)
    apply_hits    = _matches_any(APPLY_SIGNALS, norm)

    # Trusted job board URL counts as strong apply path + org
    domain = _domain_of(url)
    if domain and domain in TRUSTED_DOMAINS:
        apply_hits  = apply_hits or ["trusted_domain"]
        org_hits    = org_hits or ["trusted_domain"]

    signals_met = sum([
        bool(role_hits),
        bool(org_hits),
        bool(location_hits),
        bool(apply_hits),
    ])

    if signals_met >= 3:
        return True, min(0.60 + 0.10 * signals_met, 0.97), f"{signals_met}/4 opportunity signals met"
    if signals_met == 2:
        return True, 0.70, f"2/4 opportunity signals met"
    if signals_met == 1:
        return False, 0.75, f"Only 1/4 opportunity signal met — too vague"

    return False, 0.85, "No concrete opportunity signals (no role, org, location, or apply path)"


def stage3_classify(
    text: str,
    url: Optional[str],
    link_resolves: Optional[bool],
) -> tuple[str, float, str, list, list]:
    """
    Returns (classification, confidence, reasoning, scam_signals, outdated_signals).

    Scam requires ≥2 co-occurring red-flag signals to reduce false positives.
    Outdated: broken link + past year, OR explicit filled/closed language.
    Legit: trusted domain, or scam<2 signals and not outdated.
    """
    norm = _normalize(text)
    domain = _domain_of(url)

    # ── Outdated check ──────────────────────────────────────────
    outdated_hits = _score_signals(OUTDATED_SIGNALS, norm)

    # past_year_in_text: handled in code (pattern is None in dict)
    if _has_past_year(text) and not _has_future_or_current_year(text):
        outdated_hits["past_year_in_text"] = True

    # Broken link + past year in text → outdated
    if link_resolves is False and _has_past_year(text):
        outdated_hits["broken_link_old"] = True

    outdated_fired = [k for k, v in outdated_hits.items() if v]

    # A single strong outdated signal is enough
    if "position_filled" in outdated_fired or "past_tense_hiring" in outdated_fired:
        return "outdated", 0.88, "Explicit language indicates position closed", [], outdated_fired

    # Past year alone (no current/future year present) → outdated
    if "past_year_in_text" in outdated_fired:
        return "outdated", 0.80, f"Post contains only past year(s) — likely outdated", [], outdated_fired

    if len(outdated_fired) >= 2:
        return "outdated", 0.82, f"Outdated signals: {outdated_fired}", [], outdated_fired

    # ── Scam check ──────────────────────────────────────────────
    scam_hits = _score_signals(SCAM_SIGNALS, norm)
    scam_fired = [k for k, v in scam_hits.items() if v]

    # Trusted domain is a strong legit signal — dampens scam score
    if domain and domain in TRUSTED_DOMAINS:
        # Only flag scam if ≥3 signals despite trusted domain
        scam_threshold = 3
        legit_boost = True
    else:
        scam_threshold = 2
        legit_boost = False

    if len(scam_fired) >= scam_threshold:
        conf = min(0.55 + 0.12 * len(scam_fired), 0.93)
        return "scam", conf, f"Scam signals ({len(scam_fired)}): {scam_fired}", scam_fired, outdated_fired

    # ── Legit ───────────────────────────────────────────────────
    if legit_boost or (domain and domain in TRUSTED_DOMAINS):
        return "legit", 0.88, f"Posted on trusted job board: {domain}", scam_fired, outdated_fired

    if link_resolves is True:
        conf = 0.78 if len(scam_fired) == 0 else 0.65
        return "legit", conf, "Link resolves; no strong scam signals", scam_fired, outdated_fired

    if len(scam_fired) == 1:
        return "legit", 0.68, f"One minor scam signal ({scam_fired[0]}) — insufficient for scam label", scam_fired, outdated_fired

    if link_resolves is False:
        # Broken link but not clearly outdated → still legit but flag it
        return "legit", 0.55, "Broken link; no scam signals — possibly outdated or link error", scam_fired, outdated_fired

    return "legit", 0.72, "No scam or outdated signals detected", scam_fired, outdated_fired


# ─────────────────────────────────────────────────────────────────
# PIPELINE
# ─────────────────────────────────────────────────────────────────

class MessageValidatorPipeline:
    """
    Rule-based funnel: Stage1 → Stage2 → LinkCheck → Stage3.
    No API required.  Processes thousands of messages/second.
    """

    def process(
        self,
        message_id: str,
        text: str,
        image_path: Optional[str] = None,
    ) -> ValidationResult:
        t0 = time.perf_counter()

        text = text or ""
        has_image = bool(image_path and os.path.isfile(image_path))

        result = ValidationResult(
            message_id=message_id,
            raw_text=text,
            has_image=has_image,
        )

        url = extract_first_url(text)
        if url:
            result.link_found = url

        # ── Stage 1 ────────────────────────────────────────────
        is_job, conf1, reason1 = stage1_is_job_post(text, url)
        result.is_job_post = is_job
        result.stage_stopped_at = "stage_1"

        if not is_job:
            result.confidence = conf1
            result.reasoning = reason1
            result.processing_time_ms = (time.perf_counter() - t0) * 1000
            return result

        # ── Stage 2 ────────────────────────────────────────────
        is_real, conf2, reason2 = stage2_is_real_opportunity(text, url)
        result.is_real_opportunity = is_real
        result.stage_stopped_at = "stage_2"

        if not is_real:
            result.confidence = conf2
            result.reasoning = reason2
            result.processing_time_ms = (time.perf_counter() - t0) * 1000
            return result

        # ── Link check ─────────────────────────────────────────
        if url:
            resolves, status = check_link(url)
            result.link_resolves = resolves
            result.link_status_code = status

        # ── Stage 3 ────────────────────────────────────────────
        cls, conf3, reason3, scam_sigs, old_sigs = stage3_classify(
            text, url, result.link_resolves
        )
        result.classification = cls
        result.confidence = conf3
        result.reasoning = reason3
        result.scam_signals = scam_sigs
        result.outdated_signals = old_sigs
        result.stage_stopped_at = "stage_3"

        result.processing_time_ms = (time.perf_counter() - t0) * 1000
        return result

    def process_batch(
        self, messages: list[dict], verbose: bool = True
    ) -> list[ValidationResult]:
        results = []
        n = len(messages)
        for i, msg in enumerate(messages, 1):
            if verbose:
                img = "🖼" if msg.get("image_path") else " "
                print(f"  [{i:>5}/{n}] {img} {msg['id']:<16}", end=" ", flush=True)
            r = self.process(msg["id"], msg.get("text", ""), msg.get("image_path"))
            if verbose:
                print(f"→ {r.label():<10} ({r.stage_stopped_at})")
            results.append(r)
        return results