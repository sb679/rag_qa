from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from web.backend.routers import wechat_annotator as module
from web.backend.routers.wechat_agent_protocol import (
    KNOWLEDGE_ACQUISITION_AGENT,
    KNOWLEDGE_GOVERNANCE_AGENT,
    EVALUATION_OPTIMIZATION_AGENT,
)


class WechatAgentProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app = FastAPI()
        app.include_router(module.router, prefix="/api/wechat-annotator")
        cls.client = TestClient(app)

    def test_build_agent_observation_uses_candidate_and_local_state(self):
        with patch.object(module, "_pick_agent_account_candidate", return_value={
            "account_id": "demo_account",
            "display_name": "演示账号",
            "preferred_name": "演示账号",
            "history_urls": ["https://mp.weixin.qq.com/profile"],
        }), patch.object(module, "_infer_account_from_seed_urls", return_value=None), patch.object(module, "list_articles", return_value={"articles": [{"article_id": "a1"}, {"article_id": "a2"}]}), patch.object(module, "_filter_desktop_profiles", return_value=[{"account_id": "demo_account"}]), patch.object(module, "_has_wechat_cookie_session", return_value=True):
            payload = module._build_agent_observation({
                "search_query": "演示账号",
                "allow_desktop_fallback": True,
                "article_title": "一篇文章",
            })

        self.assertEqual(payload["resolved_account_id"], "demo_account")
        self.assertEqual(payload["matched_display_name"], "演示账号")
        self.assertTrue(payload["has_history_url"])
        self.assertTrue(payload["has_cookie_session"])
        self.assertEqual(payload["existing_article_count"], 2)
        self.assertEqual(payload["desktop_profile_count"], 1)

    def test_decide_agent_collect_action_prefers_history_url_with_cookie(self):
        decision = module._decide_agent_collect_action(
            {"capability_supported": True, "do_collect": True},
            {
                "resolved_account_id": "demo_account",
                "matched_account": {"display_name": "演示账号"},
                "has_seed_urls": False,
                "has_history_url": True,
                "has_cookie_session": True,
                "history_url": "https://mp.weixin.qq.com/profile",
            },
        )

        self.assertEqual(decision["action"], "crawl_history_url")
        self.assertEqual(decision["account_id"], "demo_account")
        self.assertEqual(decision["seed_urls"], ["https://mp.weixin.qq.com/profile"])

    def test_run_agent_clean_step_returns_skip_payload_when_no_article_ids(self):
        result = module._run_agent_clean_step({"dry_run": True, "do_ingest": False}, "demo_account", article_ids=[])

        self.assertEqual(result["skipped_reason"], "no_new_articles_to_clean")
        self.assertEqual(result["cleaned_articles"], 0)
        self.assertEqual(result["target_article_ids"], [])

    def test_build_multi_agent_orchestration_includes_protocol_and_registered_handoffs(self):
        result = {
            "steps": [],
            "task": {"task_id": "task_123", "created_at": "2026-05-16T10:00:00"},
            "governance": {
                "status": "completed",
                "artifact": {
                    "artifact_type": "governance_report",
                    "summary": "治理完成",
                    "metrics": {"risk_level": "low"},
                },
                "report": {"risk_level": "low"},
            },
        }
        parsed = {
            "trace_id": "trace_123",
            "task_type": "acquire_knowledge",
            "agent_route": [KNOWLEDGE_ACQUISITION_AGENT, KNOWLEDGE_GOVERNANCE_AGENT, EVALUATION_OPTIMIZATION_AGENT],
            "intent_label": "collect",
        }

        orchestration = module._build_multi_agent_orchestration(result, parsed, "demo_account")

        self.assertEqual(orchestration["protocol"]["agents"][0]["agent_id"], KNOWLEDGE_ACQUISITION_AGENT)
        self.assertEqual(orchestration["protocol"]["handoff_templates"][0]["input_rules"][0]["input"], "created_articles")
        self.assertTrue(any(item["to_agent"] == EVALUATION_OPTIMIZATION_AGENT for item in orchestration["handoffs"]))
        self.assertEqual(orchestration["next_agent"], EVALUATION_OPTIMIZATION_AGENT)
        self.assertIn(KNOWLEDGE_GOVERNANCE_AGENT, orchestration["completed_agents"])

    def test_governance_route_returns_protocolized_orchestration(self):
        governance_result = {
            "agent": KNOWLEDGE_GOVERNANCE_AGENT,
            "status": "completed",
            "scope": {"account_id": "demo_account", "article_count": 1},
            "report": {
                "risk_level": "low",
                "duplicate_documents": 0,
                "missing_metadata": 0,
                "content_quality_issues": 0,
                "annotation_coverage_issues": 0,
            },
            "artifact": {
                "artifact_type": "governance_report",
                "artifact_id": "governance::demo::001",
                "producer": KNOWLEDGE_GOVERNANCE_AGENT,
                "summary": "risk=low duplicates=0 missing_metadata=0",
                "location": {"source_type": "wechat", "account_id": "demo_account"},
                "metrics": {"risk_level": "low"},
            },
            "issues": [],
            "duplicate_groups": [],
            "actions": [],
            "handoff_suggestion": EVALUATION_OPTIMIZATION_AGENT,
        }

        with patch.object(module, "list_articles", return_value={"articles": [{"article_id": "article_1", "account_id": "demo_account"}]}), patch.object(module, "_load_article_payload", return_value={"article_id": "article_1", "account_id": "demo_account"}), patch.object(module, "_run_knowledge_governance_agent_for_articles", return_value=governance_result):
            response = self.client.post(
                "/api/wechat-annotator/agent/governance",
                json={"account_id": "demo_account", "article_ids": ["article_1"], "limit": 5},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["orchestration"]["protocol"]["agents"][0]["agent_id"], KNOWLEDGE_ACQUISITION_AGENT)
        self.assertEqual(payload["orchestration"]["task"]["current_agent"], KNOWLEDGE_GOVERNANCE_AGENT)
        self.assertEqual(payload["orchestration"]["next_agent"], EVALUATION_OPTIMIZATION_AGENT)

    def test_evaluation_route_returns_protocolized_orchestration(self):
        with patch.object(module, "_resolve_evaluation_snapshot", return_value={}), patch.object(module, "_record_evaluation_history", return_value=None):
            response = self.client.post(
                "/api/wechat-annotator/agent/evaluation",
                json={
                    "account_id": "demo_account",
                    "article_ids": ["article_1"],
                    "governance_report": {
                        "report": {
                            "risk_level": "low",
                            "duplicate_documents": 0,
                            "missing_metadata": 0,
                            "content_quality_issues": 0,
                            "annotation_coverage_issues": 0,
                        }
                    },
                    "shared_context": {
                        "knowledge_scope": {
                            "source_type": "wechat",
                            "account_id": "demo_account",
                            "article_ids": ["article_1"],
                        }
                    },
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["orchestration"]["protocol"]["orchestrator"], "knowledge_orchestrator")
        self.assertEqual(payload["orchestration"]["task"]["current_agent"], EVALUATION_OPTIMIZATION_AGENT)
        self.assertEqual(payload["orchestration"]["completed_agents"], [EVALUATION_OPTIMIZATION_AGENT])
        self.assertEqual(payload["orchestration"]["next_agent"], "")


if __name__ == "__main__":
    unittest.main()