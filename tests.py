"""
tests.py — Rule-Based Message Validator Test Suite
---------------------------------------------------
Run with:  python tests.py
           python tests.py -v        (verbose)
"""

import sys
import unittest
from unittest.mock import patch
from pipeline import (
    MessageValidatorPipeline,
    stage1_is_job_post,
    stage2_is_real_opportunity,
    stage3_classify,
    extract_first_url,
    check_link,
)


# FIXTURES

# ── Not a job post
MSG_SCHOLARSHIP = (
    "King Fahd 🇸🇦 Scholarship 2026 for International Students (Fully Funded)\n"
    "Apply: https://opportunitiescorners.com/king-fahd-university-scholarship-2026/\n"
    "Study Free in Saudi Arabia. Master Scholarship for International Students.\n"
    "The Scholarship covers Airfare, Meals, Accommodation, Tuition."
)

MSG_EXAM_UPDATE = (
    "FPSC Exams Update\n\n"
    "ایف پی ایس سی FPSC کے 25 اپریل سے 6 مئی تک ہونے والے امتحانات مؤخر کر دیے گئے ہیں۔\n"
    "Exams scheduled from 25 April to 06 May 2026 have been postponed.\n"
    "New Schedule to be announced soon."
)

MSG_CAREER_TIP = (
    "𝗚𝗼𝗼𝗴𝗹𝗲 𝗥𝗲𝗹𝗲𝗮𝘀𝗲𝗱 𝟭𝟬 𝗔𝗜 𝗖𝗼𝘂𝗿𝘀𝗲𝘀 𝗳𝗼𝗿 𝗙𝗥𝗘𝗘 | 𝗪𝗶𝘁𝗵 𝗙𝗿𝗲𝗲 𝗖𝗲𝗿𝘁𝗶𝗳𝗶𝗰𝗮𝘁𝗲𝘀\n"
    "Apply Link: https://fullyscholarships.com/google-ai-courses-for-free/\n"
    "Discover cutting-edge Google AI courses."
)

MSG_PERSON_SEEKING = (
    "I am looking for a job in marketing or sales. "
    "Please let me know if anyone has any leads. "
    "I have 3 years of experience. DM me."
)

MSG_VAGUE_MENTION = "You can check their job section on LinkedIn"

MSG_STUB = "AR executive"

# ── Job post but not a real opportunity 
MSG_NOT_REAL_VAGUE = (
    "We are hiring! DM us anytime if you're interested in joining our team. "
    "Great opportunity for the right candidate."
)

MSG_NOT_REAL_RUMOUR = (
    "I heard Google is hiring engineers. You should apply."
)

MSG_NOT_REAL_PLACEHOLDER = (
    "Job Opening at [COMPANY NAME]\n"
    "Position: [ROLE]\n"
    "Location: [CITY]\n"
    "We will hire the right candidate soon."
)

# ── Legit job posts 
MSG_LEGIT_FORMAL = (
    "📢 We Are Hiring – Fresh Graduates Welcome!\n"
    "Position: Office Executive / Medical Billing Support\n"
    "Company: MediMax Solutions\n"
    "Location: Commercial Market, Rawalpindi\n\n"
    "Working Hours: 5:00 PM – 2:00 AM, Monday to Friday\n\n"
    "Eligibility: Fresh graduates (Male & Female) can apply\n"
    "Good communication skills required\n\n"
    "To apply, WhatsApp your CV to: 0300-1234567"
)

MSG_LEGIT_GOVT = (
    "https://governmentjob.pk/jobs/ammunition-depot-pattoki-jobs-2026/\n\n"
    "Army Ammunition Depot Pattoki Jobs 2026 | Apply Offline (By Post/Courier Submission)"
)

MSG_LEGIT_JOBBOARD = (
    "Todays Government Jobs\n\n"
    "1: Pakistan Navy Educational Trust\n"
    "https://www.jobz.pk/pakistan-navy-educational-trust-karachi-jobs-2026.html\n"
    "Vacant Positions: Principal | English Teacher | Math Teacher | Computer Teacher\n\n"
    "2: Allama Iqbal Teaching Hospital Sialkot\n"
    "https://www.jobz.pk/allama-iqbal-memorial-teaching-hospital-sialkot-jobs-2026.html\n"
    "Vacant Positions: Medical Officer | Nurse"
)

MSG_LEGIT_SLOPPY = (
    # Sloppy grammar/formatting but actually legit (false-positive risk)
    "URGENT HIRING DENTAL BILLING\n\n"
    "RCM Specialist\nAR Executive\n\n"
    "(Both male and female are encouraged to apply)\n\n"
    "Join our growing company!\n\n"
    "📍 Location: Gulberg, Lahore\n"
    "🕒 Experience Required: 1–3 years in Dental Billing (RCM)\n"
    "💰 Salary: Market competitive (based on experience)\n\n"
    "Send CV to: hr@rcmclinic.com"
)

# ── Scam-flavored posts 
MSG_SCAM_FEE = (
    "🚀 WORK FROM HOME OPPORTUNITY 🚀\n\n"
    "Earn PKR 50,000 daily! No experience needed, no qualifications required.\n"
    "Limited seats available — act now!\n\n"
    "Registration fee: PKR 2,000 (refundable after first task)\n"
    "WhatsApp only: +923001234567\n\n"
    "Hurry! This offer expires tonight."
)

MSG_SCAM_IDENTITY_SPOOF = (
    "GOOGLE is hiring work from home agents.\n"
    "Earn USD 500 per day. No experience needed.\n"
    "WhatsApp only: +923009876543\n"
    "Registration fee required. Limited spots!"
)

MSG_SCAM_SLOPPY_BUT_LEGIT = (
    # Has one scam-like signal (urgency) but is actually a legitimate posting
    "URGENT! We need an experienced Software Engineer.\n"
    "Company: TechCorp Pvt Ltd, Islamabad (Blue Area)\n"
    "Salary: PKR 150,000 – 200,000\n"
    "Experience: 3+ years in Python/Django\n"
    "Email CV to: careers@techcorp.com.pk\n"
    "Last date to apply: 30 June 2026"
)

# ── Outdated posts
MSG_OUTDATED_FILLED = (
    "Position has been filled. Thank you for your interest.\n"
    "We were hiring for a marketing executive in Karachi."
)

MSG_OUTDATED_PAST_YEAR = (
    "We Are Hiring — Sales Manager\n"
    "Location: Lahore\n"
    "Salary: PKR 80,000\n"
    "Last Date: 15 March 2019\n"
    "Send CV to: hr@company.com"
)

# ── Broken link 
MSG_BROKEN_LINK = (
    "Latest Jobs 2020\n"
    "https://www.totally-dead-link-12345xyz.com/jobs-2020\n\n"
    "Apply for multiple positions at XYZ Corp."
)


# STAGE 1 TESTS

class TestStage1IsJobPost(unittest.TestCase):

    def test_scholarship_is_not_job(self):
        url = extract_first_url(MSG_SCHOLARSHIP)
        is_job, conf, reason = stage1_is_job_post(MSG_SCHOLARSHIP, url)
        self.assertFalse(is_job, f"Scholarship should not be a job post. Reason: {reason}")

    def test_exam_update_not_job(self):
        is_job, conf, reason = stage1_is_job_post(MSG_EXAM_UPDATE, None)
        self.assertFalse(is_job, f"Exam update should not be a job post. Reason: {reason}")

    def test_free_course_not_job(self):
        url = extract_first_url(MSG_CAREER_TIP)
        is_job, conf, reason = stage1_is_job_post(MSG_CAREER_TIP, url)
        self.assertFalse(is_job, f"Free AI course should not be a job post. Reason: {reason}")

    def test_person_seeking_job_not_post(self):
        is_job, conf, reason = stage1_is_job_post(MSG_PERSON_SEEKING, None)
        self.assertFalse(is_job, f"Person seeking job is not a job post. Reason: {reason}")

    def test_vague_mention_not_job(self):
        is_job, conf, reason = stage1_is_job_post(MSG_VAGUE_MENTION, None)
        self.assertFalse(is_job, f"'Check their job section' is not a job post. Reason: {reason}")

    def test_stub_not_job(self):
        is_job, conf, reason = stage1_is_job_post(MSG_STUB, None)
        self.assertFalse(is_job, f"Single-word stub should not be a job post. Reason: {reason}")

    def test_empty_not_job(self):
        is_job, conf, reason = stage1_is_job_post("", None)
        self.assertFalse(is_job)

    def test_legit_formal_is_job(self):
        is_job, conf, reason = stage1_is_job_post(MSG_LEGIT_FORMAL, None)
        self.assertTrue(is_job, f"Formal hiring post should be detected. Reason: {reason}")

    def test_legit_govt_is_job(self):
        url = extract_first_url(MSG_LEGIT_GOVT)
        is_job, conf, reason = stage1_is_job_post(MSG_LEGIT_GOVT, url)
        self.assertTrue(is_job, f"Govt job post should be detected. Reason: {reason}")

    def test_scam_post_is_job(self):
        is_job, conf, reason = stage1_is_job_post(MSG_SCAM_FEE, None)
        self.assertTrue(is_job, f"Scam post still is a job post at stage 1. Reason: {reason}")

    def test_confidence_above_zero(self):
        _, conf, _ = stage1_is_job_post(MSG_LEGIT_FORMAL, None)
        self.assertGreater(conf, 0)
        self.assertLessEqual(conf, 1.0)


# STAGE 2 TESTS

class TestStage2IsRealOpportunity(unittest.TestCase):

    def test_vague_hiring_not_real(self):
        """
        EDGE CASE: 'We are hiring! DM us' with no role/location/org → NOT REAL.
        Separates vague call-to-action from actionable opportunity.
        """
        is_real, conf, reason = stage2_is_real_opportunity(MSG_NOT_REAL_VAGUE, None)
        self.assertFalse(is_real, f"Vague 'DM us' post is not a real opportunity. Reason: {reason}")

    def test_rumour_not_real(self):
        is_real, conf, reason = stage2_is_real_opportunity(MSG_NOT_REAL_RUMOUR, None)
        self.assertFalse(is_real, f"Rumour/second-hand info is not real. Reason: {reason}")

    def test_placeholder_template_not_real(self):
        is_real, conf, reason = stage2_is_real_opportunity(MSG_NOT_REAL_PLACEHOLDER, None)
        self.assertFalse(is_real, f"Unfilled template is not a real opportunity. Reason: {reason}")

    def test_formal_post_is_real(self):
        is_real, conf, reason = stage2_is_real_opportunity(MSG_LEGIT_FORMAL, None)
        self.assertTrue(is_real, f"Formal post with role/org/location/apply should be real. Reason: {reason}")

    def test_govt_jobboard_is_real(self):
        url = extract_first_url(MSG_LEGIT_GOVT)
        is_real, conf, reason = stage2_is_real_opportunity(MSG_LEGIT_GOVT, url)
        self.assertTrue(is_real, f"Govt job board link should be real. Reason: {reason}")

    def test_multi_listing_is_real(self):
        url = extract_first_url(MSG_LEGIT_JOBBOARD)
        is_real, conf, reason = stage2_is_real_opportunity(MSG_LEGIT_JOBBOARD, url)
        self.assertTrue(is_real, f"Multi-job listing should be real. Reason: {reason}")

    def test_dental_billing_is_real(self):
        is_real, conf, reason = stage2_is_real_opportunity(MSG_LEGIT_SLOPPY, None)
        self.assertTrue(is_real, f"Sloppy but real job post. Reason: {reason}")


# STAGE 3 TESTS

class TestStage3Classify(unittest.TestCase):

    def test_scam_fee_plus_urgency_plus_no_exp(self):
        cls, conf, reason, scam_sigs, _ = stage3_classify(MSG_SCAM_FEE, None, None)
        self.assertEqual(cls, "scam", f"Fee + urgency + no-experience = scam. Reason: {reason}")
        self.assertGreaterEqual(len(scam_sigs), 2)

    def test_identity_spoof_scam(self):
        cls, conf, reason, scam_sigs, _ = stage3_classify(MSG_SCAM_IDENTITY_SPOOF, None, None)
        self.assertEqual(cls, "scam", f"Identity spoof + fee + no-exp = scam. Reason: {reason}")

    def test_sloppy_but_legit(self):
        """
        EDGE CASE: Post says 'URGENT' (pressure signal) but has real company,
        location, salary range, email → should be LEGIT not SCAM.
        """
        cls, conf, reason, scam_sigs, _ = stage3_classify(MSG_SCAM_SLOPPY_BUT_LEGIT, None, True)
        self.assertEqual(cls, "legit",
            f"'Urgent' alone should not trigger scam. Got: {cls}. Scam signals: {scam_sigs}. Reason: {reason}")

    def test_outdated_position_filled(self):
        cls, conf, reason, _, old_sigs = stage3_classify(MSG_OUTDATED_FILLED, None, None)
        self.assertEqual(cls, "outdated", f"Filled position should be outdated. Reason: {reason}")

    def test_outdated_past_year(self):
        cls, conf, reason, _, old_sigs = stage3_classify(MSG_OUTDATED_PAST_YEAR, None, None)
        self.assertEqual(cls, "outdated", f"2019 deadline should be outdated. Reason: {reason}")

    def test_broken_link_old_post(self):
        """
        EDGE CASE: Broken link + past year in text → OUTDATED.
        """
        url = extract_first_url(MSG_BROKEN_LINK)
        cls, conf, reason, _, old_sigs = stage3_classify(MSG_BROKEN_LINK, url, False)
        self.assertEqual(cls, "outdated",
            f"Broken link + '2020' in text should be outdated. Reason: {reason}")

    def test_trusted_domain_is_legit(self):
        url = extract_first_url(MSG_LEGIT_GOVT)
        cls, conf, reason, _, _ = stage3_classify(MSG_LEGIT_GOVT, url, True)
        self.assertEqual(cls, "legit", f"Trusted domain governmentjob.pk should be legit. Reason: {reason}")

    def test_legit_formal_post(self):
        cls, conf, reason, _, _ = stage3_classify(MSG_LEGIT_FORMAL, None, None)
        self.assertEqual(cls, "legit", f"Formal post with email should be legit. Reason: {reason}")

    def test_confidence_in_range(self):
        cls, conf, reason, _, _ = stage3_classify(MSG_LEGIT_FORMAL, None, None)
        self.assertGreater(conf, 0)
        self.assertLessEqual(conf, 1.0)


# FULL PIPELINE TESTS

class TestFullPipeline(unittest.TestCase):

    def setUp(self):
        self.pipeline = MessageValidatorPipeline()

    def _run(self, text, mock_link=None):
        """Run pipeline with optional mocked link result."""
        if mock_link is not None:
            with patch("pipeline.check_link", return_value=mock_link):
                return self.pipeline.process("TEST_01", text)
        else:
            with patch("pipeline.check_link", return_value=(None, 0)):
                return self.pipeline.process("TEST_01", text)

    # ── End-to-end Stage 1 exits ────────────────────────────────

    def test_pipeline_scholarship_exits_stage1(self):
        r = self._run(MSG_SCHOLARSHIP)
        self.assertFalse(r.is_job_post)
        self.assertEqual(r.stage_stopped_at, "stage_1")
        self.assertEqual(r.label(), "NOT-JOB")

    def test_pipeline_exam_update_exits_stage1(self):
        r = self._run(MSG_EXAM_UPDATE)
        self.assertEqual(r.label(), "NOT-JOB")

    # ── End-to-end Stage 2 exits 

    def test_pipeline_vague_exits_stage2(self):
        """EDGE CASE: Job-mentioning message that isn't a real opportunity."""
        r = self._run(MSG_NOT_REAL_VAGUE)
        # May exit at stage 1 OR stage 2 — either is correct
        self.assertFalse(r.is_real_opportunity,
            f"Vague 'DM us' should not be a real opportunity. Label: {r.label()}")

    def test_pipeline_placeholder_exits_stage2(self):
        r = self._run(MSG_NOT_REAL_PLACEHOLDER)
        self.assertFalse(r.is_real_opportunity)

    # ── End-to-end Stage 3 classifications 

    def test_pipeline_scam_classified(self):
        r = self._run(MSG_SCAM_FEE)
        if r.stage_stopped_at == "stage_3":
            self.assertEqual(r.classification, "scam",
                f"Fee+urgency+no-exp should be scam. Reasoning: {r.reasoning}")

    def test_pipeline_sloppy_legit_not_scam(self):
        """
        EDGE CASE: Scam-flavored post that is actually legit.
        'URGENT' keyword alone should NOT classify as scam.
        """
        r = self._run(MSG_SCAM_SLOPPY_BUT_LEGIT, mock_link=(True, 200))
        if r.stage_stopped_at == "stage_3":
            self.assertNotEqual(r.classification, "scam",
                f"Single urgency signal should not = scam. Reasoning: {r.reasoning}")

    def test_pipeline_broken_link_outdated(self):
        """EDGE CASE: Broken link resolution."""
        r = self._run(MSG_BROKEN_LINK, mock_link=(False, 404))
        self.assertIsNotNone(r.link_found)
        if r.stage_stopped_at == "stage_3":
            self.assertEqual(r.link_resolves, False)
            self.assertEqual(r.classification, "outdated",
                f"Broken link + old year should be outdated. Reasoning: {r.reasoning}")

    def test_pipeline_outdated_filled(self):
        r = self._run(MSG_OUTDATED_FILLED)
        if r.stage_stopped_at == "stage_3":
            self.assertEqual(r.classification, "outdated")

    def test_pipeline_legit_formal(self):
        r = self._run(MSG_LEGIT_FORMAL)
        self.assertTrue(r.is_job_post)
        self.assertTrue(r.is_real_opportunity)
        self.assertEqual(r.stage_stopped_at, "stage_3")
        self.assertEqual(r.classification, "legit")

    def test_pipeline_legit_govt_jobboard(self):
        r = self._run(MSG_LEGIT_GOVT, mock_link=(True, 200))
        self.assertTrue(r.is_job_post)
        self.assertEqual(r.classification, "legit")

    # ── Result structure tests 

    def test_result_has_processing_time(self):
        r = self._run(MSG_LEGIT_FORMAL)
        self.assertGreater(r.processing_time_ms, 0)

    def test_result_to_dict_serializable(self):
        import json
        r = self._run(MSG_LEGIT_FORMAL)
        d = r.to_dict()
        # Should not raise
        json.dumps(d)

    def test_empty_message(self):
        r = self._run("")
        self.assertFalse(r.is_job_post)
        self.assertEqual(r.stage_stopped_at, "stage_1")

    def test_batch_processing(self):
        messages = [
            {"id": "T1", "text": MSG_SCHOLARSHIP},
            {"id": "T2", "text": MSG_LEGIT_FORMAL},
            {"id": "T3", "text": MSG_SCAM_FEE},
            {"id": "T4", "text": MSG_NOT_REAL_VAGUE},
            {"id": "T5", "text": MSG_OUTDATED_FILLED},
        ]
        with patch("pipeline.check_link", return_value=(None, 0)):
            results = self.pipeline.process_batch(messages, verbose=False)
        self.assertEqual(len(results), 5)
        labels = {r.message_id: r.label() for r in results}
        self.assertEqual(labels["T1"], "NOT-JOB")
        self.assertEqual(labels["T2"], "LEGIT")


# UTILITY TESTS

class TestUtilities(unittest.TestCase):

    def test_extract_url_http(self):
        url = extract_first_url("Apply here: https://example.com/jobs")
        self.assertEqual(url, "https://example.com/jobs")

    def test_extract_url_www(self):
        url = extract_first_url("Visit www.jobz.pk for more info")
        self.assertEqual(url, "https://www.jobz.pk")

    def test_extract_url_none(self):
        url = extract_first_url("No link here")
        self.assertIsNone(url)

    def test_extract_url_strips_trailing_punctuation(self):
        url = extract_first_url("See https://example.com/jobs. Apply now.")
        self.assertFalse(url.endswith("."))

    def test_check_link_invalid_domain(self):
        resolves, code = check_link("https://totally-nonexistent-xyz12345.com", timeout=3)
        self.assertFalse(resolves)


# MAIN

if __name__ == "__main__":
    verbosity = 2 if "-v" in sys.argv else 1
    loader = unittest.TestLoader()
    suite  = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestStage1IsJobPost))
    suite.addTests(loader.loadTestsFromTestCase(TestStage2IsRealOpportunity))
    suite.addTests(loader.loadTestsFromTestCase(TestStage3Classify))
    suite.addTests(loader.loadTestsFromTestCase(TestFullPipeline))
    suite.addTests(loader.loadTestsFromTestCase(TestUtilities))

    runner = unittest.TextTestRunner(verbosity=verbosity)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
