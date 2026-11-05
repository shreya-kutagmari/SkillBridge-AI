
import unittest

from utils.resume_analyzer import analyze_resume


class TestResumeAnalyzer(unittest.TestCase):

    def setUp(self):
        self.sample_resume = """
        CONTACT
        test@example.com
        9876543210

        PROFESSIONAL SUMMARY
        Entry-level software developer with Python skills.

        EDUCATION
        B.E. Electronics and Communication Engineering

        WORK EXPERIENCE
        Software development intern.

        PROJECTS
        Developed an Air Quality Monitoring System using Arduino Uno.
        Implemented sensor-based monitoring.

        TECHNICAL SKILLS
        Python, SQL, HTML, CSS, Arduino

        CERTIFICATIONS
        Google Cloud Engineer Track
        """

    def test_returns_expected_fields(self):
        result = analyze_resume(self.sample_resume)

        expected_fields = [
            "score",
            "score_breakdown",
            "detected_sections",
            "missing_sections",
            "skills",
            "project_entry_count",
            "suggestions",
            "disclaimer"
        ]

        for field in expected_fields:
            self.assertIn(field, result)

    def test_score_is_between_zero_and_100(self):
        result = analyze_resume(self.sample_resume)

        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 100)

    def test_detects_education_and_projects(self):
        result = analyze_resume(self.sample_resume)

        self.assertIn("education", result["detected_sections"])
        self.assertIn("projects", result["detected_sections"])

    def test_empty_resume(self):
        result = analyze_resume("")

        self.assertEqual(result["score"], 0)
        self.assertIsInstance(result["suggestions"], list)

    def test_disclaimer_is_present(self):
        result = analyze_resume(self.sample_resume)

        self.assertTrue(result["disclaimer"])


if __name__ == "__main__":
    unittest.main()
