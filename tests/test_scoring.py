import datetime as dt
import unittest

from filters import score_vacancy
from hh_bot import format_message


NOW = dt.datetime(2026, 9, 28, 15, 0, tzinfo=dt.timezone.utc)


def vacancy(name: str, description: str, **extra):
    result = {
        "name": name,
        "description": description,
        "published_at": "2026-09-28T14:00:00+00:00",
        "employer": {"name": "Test Client"},
    }
    result.update(extra)
    return result


class ScoringTests(unittest.TestCase):
    def test_ai_video_remote_project_with_provided_access_is_strong_and_low_risk(self):
        fit = score_vacancy(
            vacancy(
                "AI Video Creator / Higgsfield",
                "Runway, Veo, Kling, CapCut. We provide access to Higgsfield and cover subscriptions.",
                work_format=[{"id": "REMOTE"}],
                employment_form={"id": "PROJECT"},
                salary_range={"from": 120000, "to": 180000, "currency": "RUR"},
            ),
            now=NOW,
        )
        self.assertTrue(fit.is_fit)
        self.assertGreaterEqual(fit.fit_score, 85)
        self.assertEqual(fit.money_risk, 0)
        self.assertEqual(fit.credit_status, "provided")
        self.assertTrue(any("AI-доступы" in x for x in fit.positive_flags))
        self.assertTrue(fit.remote)
        self.assertTrue(fit.project)

    def test_simple_automation_bot_parser_and_api_are_prioritized(self):
        fit = score_vacancy(
            vacancy(
                "Telegram bot and API integration",
                "Simple AI automation in n8n: Telegram bot, parser, webhook and API integration.",
                work_format=[{"id": "REMOTE"}],
                employment_form={"id": "PROJECT"},
            ),
            now=NOW,
        )
        self.assertGreaterEqual(fit.fit_score, 80)
        self.assertIn("Simple AI automation", fit.categories)
        self.assertIn("Telegram bots / parsers / API", fit.categories)

    def test_simple_3d_is_prioritized(self):
        fit = score_vacancy(
            vacancy(
                "Blender 3D modeler",
                "Simple 3D modeling and renders in Blender for product cards.",
                employment_form={"id": "PROJECT"},
            ),
            now=NOW,
        )
        self.assertTrue(fit.is_fit)
        self.assertIn("Simple 3D", fit.categories)
        self.assertGreaterEqual(fit.fit_score, 60)

    def test_own_paid_subscriptions_raise_money_risk(self):
        fit = score_vacancy(
            vacancy(
                "AI Video Creator",
                "Higgsfield and Runway. Must use your own subscriptions and accounts.",
            ),
            now=NOW,
        )
        self.assertEqual(fit.credit_status, "own")
        self.assertGreaterEqual(fit.money_risk, 45)
        self.assertTrue(any("свои платные" in x for x in fit.risks))

    def test_paid_tools_without_cost_owner_are_flagged(self):
        fit = score_vacancy(
            vacancy("AI Video Creator", "Create videos in Higgsfield and Runway."),
            now=NOW,
        )
        self.assertEqual(fit.credit_status, "unspecified")
        self.assertGreaterEqual(fit.money_risk, 18)

    def test_senior_backend_devops_ml_stack_gets_strong_penalty(self):
        fit = score_vacancy(
            vacancy(
                "Senior Backend / ML Engineer",
                "Build an LLM platform with FastAPI, PostgreSQL, Redis, Kubernetes, MLOps and system design.",
            ),
            now=NOW,
        )
        self.assertFalse(fit.is_fit)
        self.assertLess(fit.fit_score, 45)
        self.assertGreaterEqual(fit.money_risk, 38)
        self.assertTrue(any("Senior Backend" in x for x in fit.risks))

    def test_system_design_kubernetes_production_stack_gets_strong_penalty(self):
        fit = score_vacancy(
            vacancy(
                "LLM automation developer",
                "System design for production-grade distributed systems on Kubernetes and PostgreSQL.",
            ),
            now=NOW,
        )
        self.assertLess(fit.fit_score, 45)
        self.assertGreaterEqual(fit.money_risk, 32)
        self.assertTrue(any("production/backend/ML" in x for x in fit.risks))

    def test_coding_heavy_stack_is_a_separate_risk(self):
        fit = score_vacancy(
            vacancy(
                "AI automation specialist",
                "Advanced Python, code review, unit testing and software architecture are mandatory.",
            ),
            now=NOW,
        )
        self.assertGreaterEqual(fit.money_risk, 22)
        self.assertTrue(any("coding-heavy" in x for x in fit.risks))

    def test_high_volume_and_full_time_risks_accumulate(self):
        fit = score_vacancy(
            vacancy(
                "AI Video Creator",
                "Produce 10 videos per day in a high-volume full-time role, 40+ hours per week.",
                schedule={"id": "fullDay"},
            ),
            now=NOW,
        )
        self.assertGreaterEqual(fit.money_risk, 52)
        self.assertTrue(any("скорость/объём" in x for x in fit.risks))
        self.assertTrue(any("full-time" in x for x in fit.risks))

    def test_irrelevant_job_does_not_match(self):
        fit = score_vacancy(
            vacancy("Кладовщик", "Работа на складе, учёт товара"),
            now=NOW,
        )
        self.assertFalse(fit.is_fit)

    def test_telegram_message_shows_both_scores(self):
        item = vacancy(
            "AI Video Creator",
            "Higgsfield. We provide access to Higgsfield.",
            alternate_url="https://example.invalid/job",
        )
        fit = score_vacancy(item, now=NOW)
        message = format_message(item, fit)
        self.assertIn(f"Fit {fit.fit_score} / Money Risk {fit.money_risk}", message)
        self.assertIn("Позитивные флаги", message)


if __name__ == "__main__":
    unittest.main()
