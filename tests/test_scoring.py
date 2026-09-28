import datetime as dt
import unittest

from filters import score_vacancy


NOW = dt.datetime(2026, 9, 28, 15, 0, tzinfo=dt.timezone.utc)


class ScoringTests(unittest.TestCase):
    def test_ai_video_remote_project_is_strong(self):
        vacancy = {
            "name": "AI Video Creator / Higgsfield",
            "description": "Runway, Veo, Kling, CapCut. We provide access to Higgsfield.",
            "work_format": [{"id": "REMOTE"}],
            "employment_form": {"id": "PROJECT"},
            "published_at": "2026-09-28T14:20:00+00:00",
            "salary_range": {"from": 120000, "to": 180000, "currency": "RUR"},
            "employer": {"name": "Studio"},
        }
        fit = score_vacancy(vacancy, now=NOW)
        self.assertTrue(fit.is_fit)
        self.assertGreaterEqual(fit.score, 80)
        self.assertEqual(fit.credit_status, "provided")
        self.assertTrue(fit.remote)
        self.assertTrue(fit.project)

    def test_own_paid_subscriptions_are_a_risk(self):
        vacancy = {
            "name": "AI Video Creator",
            "description": "Higgsfield, Runway. Must use your own subscriptions and accounts.",
            "published_at": "2026-09-28T12:00:00+00:00",
            "employer": {"name": "Agency"},
        }
        fit = score_vacancy(vacancy, now=NOW)
        self.assertEqual(fit.credit_status, "own")
        self.assertTrue(any("свои платные" in x for x in fit.risks))

    def test_heavy_backend_role_is_penalized(self):
        vacancy = {
            "name": "Senior Backend Developer",
            "description": "Python FastAPI PostgreSQL Redis Kubernetes. Build an LLM service.",
            "published_at": "2026-09-28T14:00:00+00:00",
            "employer": {"name": "Tech"},
        }
        fit = score_vacancy(vacancy, now=NOW)
        self.assertTrue(any("backend" in x for x in fit.risks))
        self.assertLess(fit.score, 80)

    def test_irrelevant_job_does_not_match(self):
        vacancy = {
            "name": "Кладовщик",
            "description": "Работа на складе, учёт товара",
            "published_at": "2026-09-28T14:00:00+00:00",
            "employer": {"name": "Warehouse"},
        }
        fit = score_vacancy(vacancy, now=NOW)
        self.assertFalse(fit.is_fit)


if __name__ == "__main__":
    unittest.main()
