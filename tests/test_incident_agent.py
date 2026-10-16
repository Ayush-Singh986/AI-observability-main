import importlib.util
import unittest
import base64
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
AGENT_PATH = PROJECT_ROOT / "scripts" / "incident-agent.py"
SPEC = importlib.util.spec_from_file_location("incident_agent", AGENT_PATH)
incident_agent = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(incident_agent)


class IncidentAgentTests(unittest.TestCase):
    def test_oom_from_previous_termination_takes_priority_over_crash_loop(self):
        pod = SimpleNamespace(
            metadata=SimpleNamespace(
                name="paymentservice-abc",
                namespace="online-boutique",
                uid="pod-uid",
                labels={"app": "paymentservice"},
            ),
            status=SimpleNamespace(
                container_statuses=[
                    SimpleNamespace(
                        name="server",
                        restart_count=3,
                        state=SimpleNamespace(
                            waiting=SimpleNamespace(
                                reason="CrashLoopBackOff",
                                message="back-off restarting failed container",
                            ),
                            terminated=None,
                        ),
                        last_state=SimpleNamespace(
                            terminated=SimpleNamespace(
                                reason="OOMKilled",
                                message="container exceeded memory limit",
                            )
                        ),
                    )
                ]
            ),
            spec=SimpleNamespace(
                containers=[SimpleNamespace(name="server", image="example/payment:v1")]
            ),
        )

        incidents = incident_agent.get_incidents(pod)

        self.assertEqual(len(incidents), 1)
        self.assertEqual(incidents[0].reason, "OOMKilled")
        self.assertEqual(incidents[0].service, "paymentservice")

    def test_agent_does_not_report_its_own_pod(self):
        pod = SimpleNamespace(
            metadata=SimpleNamespace(
                name="incident-agent-abc",
                namespace="online-boutique",
                uid="agent-uid",
                labels={"app": "incident-agent"},
            ),
            status=SimpleNamespace(container_statuses=[]),
            spec=SimpleNamespace(containers=[]),
        )

        self.assertEqual(incident_agent.get_incidents(pod), [])

    def test_watcher_rbac_has_no_kubernetes_write_permissions(self):
        yaml = incident_agent.YAML()
        resources = list(
            yaml.load_all(
                (PROJECT_ROOT / "release" / "incident-agent-rbac.yaml").read_text(
                    encoding="utf-8"
                )
            )
        )
        role = next(resource for resource in resources if resource["kind"] == "Role")
        verbs = {
            verb
            for rule in role["rules"]
            for verb in rule["verbs"]
        }

        self.assertEqual(verbs, {"get", "list", "watch"})
        self.assertEqual(role["metadata"]["namespace"], "online-boutique")

    def test_sanitizes_common_secrets_personal_data_and_large_logs(self):
        value = "Authorization: Bearer abc123 api_key=secret email user@example.com card 4111111111111111 "
        sanitized = incident_agent.sanitize_logs(value)
        truncated = incident_agent.sanitize_logs("x" * 13000)

        self.assertIn("Authorization: [REDACTED]", sanitized)
        self.assertIn("api_key=[REDACTED]", sanitized)
        self.assertNotIn("user@example.com", sanitized)
        self.assertNotIn("4111111111111111", sanitized)
        self.assertEqual(len(truncated), incident_agent.MAX_LOG_CHARS)

    def test_proposal_changes_only_target_container_memory(self):
        manifest = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: paymentservice
spec:
  template:
    spec:
      containers:
        - name: server
          resources:
            requests:
              cpu: 100m
              memory: 100Mi
            limits:
              cpu: 200m
              memory: 100Mi
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: frontend
spec:
  replicas: 2
"""

        proposal = incident_agent.create_manifest_proposal(
            manifest,
            "paymentservice",
            "server",
            "128Mi",
            "256Mi",
        )

        yaml = incident_agent.YAML()
        old_documents = list(yaml.load_all(manifest))
        new_documents = list(yaml.load_all(proposal))
        self.assertEqual(len(old_documents), len(new_documents))
        old_documents[0]["spec"]["template"]["spec"]["containers"][0]["resources"]["requests"]["memory"] = "128Mi"
        old_documents[0]["spec"]["template"]["spec"]["containers"][0]["resources"]["limits"]["memory"] = "256Mi"
        self.assertEqual(old_documents, new_documents)

    def test_refuses_unsafe_memory_values(self):
        manifest = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: paymentservice
spec:
  template:
    spec:
      containers:
        - name: server
          resources:
            requests:
              memory: 100Mi
            limits:
              memory: 100Mi
"""
        with self.assertRaisesRegex(RuntimeError, "cannot exceed"):
            incident_agent.create_manifest_proposal(
                manifest,
                "paymentservice",
                "server",
                "512Mi",
                "256Mi",
            )
        with self.assertRaisesRegex(RuntimeError, "2Gi safety cap"):
            incident_agent.create_manifest_proposal(
                manifest,
                "paymentservice",
                "server",
                "3Gi",
                "3Gi",
            )
        with self.assertRaisesRegex(RuntimeError, "must not be lower"):
            incident_agent.create_manifest_proposal(
                manifest,
                "paymentservice",
                "server",
                "50Mi",
                "256Mi",
            )

    def test_never_proposes_changes_for_another_container_or_deployment(self):
        manifest = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: paymentservice
spec:
  template:
    spec:
      containers:
        - name: server
          resources:
            requests:
              memory: 100Mi
            limits:
              memory: 100Mi
"""
        with self.assertRaisesRegex(RuntimeError, "was not found"):
            incident_agent.create_manifest_proposal(
                manifest,
                "frontend",
                "server",
                "128Mi",
                "256Mi",
            )
        with self.assertRaisesRegex(RuntimeError, "was not found"):
            incident_agent.create_manifest_proposal(
                manifest,
                "paymentservice",
                "unknown-container",
                "128Mi",
                "256Mi",
            )

    def test_ai_cannot_return_unvalidated_remediation_types(self):
        response = {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"summary":"Investigating","confidence":0.9,'
                            '"safe_remediation":"yes","memory_request":"128Mi",'
                            '"memory_limit":"256Mi"}'
                        )
                    }
                }
            ]
        }
        incident = incident_agent.Incident(
            namespace="online-boutique",
            pod_name="paymentservice-abc",
            pod_uid="uid",
            service="paymentservice",
            container="server",
            reason="OOMKilled",
            restart_count=1,
            image="ecr/paymentservice:v1",
            message="oom",
        )
        with patch.object(incident_agent, "http_json", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "safe_remediation as a boolean"):
                incident_agent.call_ai(
                    "https://api.example.com/v1",
                    "test-key",
                    "test-model",
                    incident,
                    "redacted logs",
                    [],
                )

    def test_review_pull_request_is_draft_and_only_updates_manifest(self):
        manifest = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: paymentservice
spec:
  template:
    spec:
      containers:
        - name: server
          resources:
            requests:
              memory: 100Mi
            limits:
              memory: 100Mi
"""
        calls = []
        def github_request(_api_url, _token, path, *, method="GET", body=None):
            calls.append((method, path, body))
            if method == "GET" and "/pulls?" in path:
                return []
            if method == "GET" and "/contents/" in path:
                return {
                    "content": base64.b64encode(manifest.encode()).decode(),
                    "sha": "source-file-sha",
                }
            if method == "GET" and "/git/ref/" in path:
                return {"object": {"sha": "base-commit-sha"}}
            if method == "POST" and path.endswith("/pulls"):
                return {"html_url": "https://github.com/example/repo/pull/42"}
            return {}

        incident = incident_agent.Incident(
            namespace="online-boutique",
            pod_name="paymentservice-abc",
            pod_uid="pod-uid",
            service="paymentservice",
            container="server",
            reason="OOMKilled",
            restart_count=1,
            image="ecr/paymentservice:v1",
            message="oom",
        )
        deployment = [{"commit_sha": "abcdef123456"}]
        with patch.object(incident_agent, "github_request", side_effect=github_request):
            pull_url = incident_agent.create_review_pr(
                "https://api.github.com",
                "test-token",
                "example",
                "repo",
                "main",
                incident,
                "Observed memory termination",
                0.9,
                "128Mi",
                "256Mi",
                deployment,
            )

        self.assertEqual(pull_url, "https://github.com/example/repo/pull/42")
        pull_request = next(body for method, path, body in calls if method == "POST" and path.endswith("/pulls"))
        self.assertTrue(pull_request["draft"])
        self.assertIn("review the pod logs", pull_request["body"].lower())
        update = next(body for method, path, body in calls if method == "PUT" and "/contents/" in path)
        proposed = base64.b64decode(update["content"]).decode()
        parsed = list(incident_agent.YAML().load_all(proposed))[0]
        resources = parsed["spec"]["template"]["spec"]["containers"][0]["resources"]
        self.assertEqual(resources["requests"]["memory"], "128Mi")
        self.assertEqual(resources["limits"]["memory"], "256Mi")


if __name__ == "__main__":
    unittest.main()
