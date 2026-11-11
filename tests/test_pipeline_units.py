"""Unit tests (unittest — no pytest dependency).

Covered:
  * filter pass/fail decisions come with the right human-readable reasons
  * email extraction honesty: no email in description -> "Not Found"
  * generated messages respect the word-count bounds (email 60-90, DM 15-30)
  * sending layer deduplication: a second run sends 0 new messages

Run:  python -m unittest discover -s tests -v
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from outreach.models import Influencer
from outreach import filtering, personalization, sending
from outreach.enrichment import extract_email


def make_inf(**kw):
    base = dict(
        channel_id="UCtest123",
        name="Fit With Priya",
        profile_url="https://www.youtube.com/@fitwithpriya",
        source_url="https://www.youtube.com/@fitwithpriya/videos",
        subscribers=42000,
        description="Home workouts and yoga for busy people.",
        recent_videos=[{"title": "20 Min Full Body Home Workout", "views": 3000},
                       {"title": "Morning Yoga for Beginners", "views": 2600}],
        avg_views=2800.0,
        engagement_rate=6.67,
        themes=["home workouts", "yoga"],
    )
    base.update(kw)
    return Influencer(**base)


class FilterTests(unittest.TestCase):
    def test_passing_record(self):
        inf = make_inf()
        filtering.classify(inf)
        self.assertEqual(inf.status, "Passed")
        self.assertIn("Passed:", inf.filter_reason)

    def test_below_band_fails_with_reason(self):
        inf = make_inf(subscribers=3200)
        filtering.classify(inf)
        self.assertEqual(inf.status, "Failed")
        self.assertIn("Below the micro-influencer band", inf.filter_reason)
        self.assertIn("3,200", inf.filter_reason)

    def test_above_band_fails_with_reason(self):
        inf = make_inf(subscribers=850000)
        filtering.classify(inf)
        self.assertEqual(inf.status, "Failed")
        self.assertIn("Above the micro-influencer band", inf.filter_reason)

    def test_unavailable_subscribers_fails(self):
        inf = make_inf(subscribers=None)
        filtering.classify(inf)
        self.assertEqual(inf.status, "Failed")
        self.assertIn("not displayed", inf.filter_reason)

    def test_no_fitness_theme_fails(self):
        inf = make_inf(themes=[])
        filtering.classify(inf)
        self.assertEqual(inf.status, "Failed")
        self.assertIn("No fitness content themes", inf.filter_reason)

    def test_low_engagement_fails(self):
        inf = make_inf(engagement_rate=0.42)
        filtering.classify(inf)
        self.assertEqual(inf.status, "Failed")
        self.assertIn("Engagement below threshold", inf.filter_reason)

    def test_unavailable_engagement_fails(self):
        inf = make_inf(engagement_rate=None)
        filtering.classify(inf)
        self.assertEqual(inf.status, "Failed")
        self.assertIn("Engagement rate unavailable", inf.filter_reason)


class EmailExtractionTests(unittest.TestCase):
    def test_no_email_in_description_is_not_found(self):
        desc = "Welcome to my channel! New workouts every Monday and Friday."
        self.assertEqual(extract_email(desc), "Not Found")

    def test_empty_description_is_not_found(self):
        self.assertEqual(extract_email(""), "Not Found")

    def test_real_email_is_extracted_verbatim(self):
        desc = "For business inquiries contact me at hello@fitwithpriya.com anytime."
        self.assertEqual(extract_email(desc), "hello@fitwithpriya.com")

    def test_placeholder_email_is_rejected(self):
        desc = "Reach us via name@example.com for details."
        self.assertEqual(extract_email(desc), "Not Found")


class PersonalizationTests(unittest.TestCase):
    def _check_bounds(self, inf, idx):
        personalization.generate_messages(inf, angle_index=idx)
        email_words = len(inf.email_pitch.split())
        dm_words = len(inf.dm_text.split())
        self.assertTrue(60 <= email_words <= 90,
                        f"email words {email_words} out of 60-90: {inf.email_pitch}")
        self.assertTrue(15 <= dm_words <= 30,
                        f"DM words {dm_words} out of 15-30: {inf.dm_text}")

    def test_word_count_bounds_for_all_angles(self):
        for i in range(len(personalization.ANGLES)):
            self._check_bounds(make_inf(), i)

    def test_word_count_bounds_varied_profiles(self):
        profiles = [
            dict(name="YogaWithAna", subscribers=5100, avg_views=900.0,
                 themes=["yoga"], recent_videos=[{"title": "Sunrise Yoga Flow", "views": 900}]),
            dict(name="The Kettlebell Coach Official Channel", subscribers=99900,
                 avg_views=12000.0, themes=["strength training"],
                 recent_videos=[{"title": "Kettlebell Swings: The Only Guide You Will Ever Need To Master This Move", "views": 12000}]),
            dict(name="DanceFit", subscribers=12500, avg_views=4000.0,
                 themes=["dance fitness"],
                 recent_videos=[{"title": "Zumba Party", "views": 4000}]),
        ]
        for j, p in enumerate(profiles):
            self._check_bounds(make_inf(**p), j)

    def test_word_count_bounds_for_brand_style_names(self):
        # Regression: channel names that are brands, not people, and long
        # video titles must still produce in-bounds messages.
        profiles = [
            dict(name="Move With Anabelle", themes=["pilates"],
                 recent_videos=[{"title": "30 Min Wall Pilates For A Flat Stomach And Toned Glutes At Home", "views": 5000}]),
            dict(name="Improved Health Chair Workouts", themes=["low-impact & rehab"],
                 recent_videos=[{"title": "Chair Yoga", "views": 8000}]),
            dict(name="Pregnancy With Melissa", themes=["yoga"],
                 recent_videos=[{"title": "10-Min Pregnancy Stretches For Easier Birth And Less Pain", "views": 9000}]),
        ]
        for j, p in enumerate(profiles):
            self._check_bounds(make_inf(**p), j + 1)

    def test_messages_reference_the_influencer(self):
        inf = make_inf()
        personalization.generate_messages(inf, angle_index=0)
        self.assertIn("Fit With Priya", inf.email_pitch)
        self.assertIn("home workouts", inf.email_pitch.lower())
        self.assertIn("sponsorship", inf.collab_angle)


class SendingDedupTests(unittest.TestCase):
    def test_second_run_sends_zero_new(self):
        inf = make_inf(email="hello@fitwithpriya.com", status="Passed",
                       email_subject="s", email_pitch="pitch")
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "state.sqlite")
            first, skipped1, rows1 = sending.send_all([inf], db, live=False)
            self.assertEqual(first, 1)
            self.assertEqual(len(rows1), 1)
            self.assertEqual(rows1[0]["Sent"], "Yes")
            self.assertEqual(rows1[0]["Status"], "Sent (simulated)")

            second, skipped2, rows2 = sending.send_all([inf], db, live=False)
            self.assertEqual(second, 0, "re-run must not re-send")
            self.assertEqual(skipped2, 1)
            self.assertEqual(len(rows2), 1)

    def test_passed_without_email_is_not_sent(self):
        inf = make_inf(email="Not Found", status="Passed", email_pitch="pitch")
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "state.sqlite")
            new_sends, _, rows = sending.send_all([inf], db, live=False)
            self.assertEqual(new_sends, 0)
            self.assertEqual(rows[0]["Sent"], "No")
            self.assertIn("no public email", rows[0]["Status"])


if __name__ == "__main__":
    unittest.main()
