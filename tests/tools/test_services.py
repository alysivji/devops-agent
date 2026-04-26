from pathlib import Path

import pytest

from devops_bot.history import RunHistory, reset_active_run_history, set_active_run_history
from devops_bot.tools.services import service_get, service_list, service_upsert


class TestServiceList:
    def test_service_list_reads_valid_registry(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        registry_path = tmp_path / "services" / "registry.yaml"
        registry_path.parent.mkdir(parents=True)
        registry_path.write_text(
            "- name: grafana\n"
            "  description: Control-node Grafana instance for dashboards.\n"
            "  runtime: systemd\n"
            "  location: control\n"
            "  status: expected\n"
            "  managed_by: ansible/playbooks/install-grafana.yaml\n"
            "  endpoints:\n"
            "    - name: health\n"
            "      url: http://127.0.0.1:3000/api/health\n"
            "      protocol: http\n"
            "      scope: control-node-local\n"
            "  tags:\n"
            "    - monitoring\n"
            "    - dashboards\n",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)

        assert service_list() == [
            {
                "name": "grafana",
                "description": "Control-node Grafana instance for dashboards.",
                "runtime": "systemd",
                "location": "control",
                "status": "expected",
                "managed_by": "ansible/playbooks/install-grafana.yaml",
                "tags": ["monitoring", "dashboards"],
            }
        ]

    def test_service_list_returns_empty_list_when_missing(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.chdir(tmp_path)

        assert service_list() == []

    def test_service_list_rejects_invalid_top_level_shape(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        registry_path = tmp_path / "services" / "registry.yaml"
        registry_path.parent.mkdir(parents=True)
        registry_path.write_text("services:\n  - name: grafana\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        with pytest.raises(ValueError, match="must be a list"):
            service_list()

    def test_service_list_rejects_missing_required_service_fields(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        registry_path = tmp_path / "services" / "registry.yaml"
        registry_path.parent.mkdir(parents=True)
        registry_path.write_text("- name: grafana\n  runtime: systemd\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        with pytest.raises(ValueError, match="Invalid service registry entry"):
            service_list()

    def test_service_list_rejects_endpoint_without_url_or_host_port(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        registry_path = tmp_path / "services" / "registry.yaml"
        registry_path.parent.mkdir(parents=True)
        registry_path.write_text(
            "- name: nginx\n"
            "  description: Kubernetes nginx service.\n"
            "  runtime: kubernetes\n"
            "  location: default\n"
            "  status: expected\n"
            "  managed_by: helm/charts/nginx\n"
            "  endpoints:\n"
            "    - name: http\n"
            "      protocol: http\n"
            "  tags:\n"
            "    - web\n",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)

        with pytest.raises(ValueError, match="either `url` or both `host` and `port`"):
            service_list()

    def test_service_list_records_run_history(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        registry_path = tmp_path / "services" / "registry.yaml"
        registry_path.parent.mkdir(parents=True)
        registry_path.write_text(
            "- name: prometheus\n"
            "  description: Control-node Prometheus server for scraping metrics.\n"
            "  runtime: systemd\n"
            "  location: control\n"
            "  status: expected\n"
            "  managed_by: ansible/playbooks/install-prometheus.yaml\n"
            "  endpoints:\n"
            "    - name: readiness\n"
            "      url: http://127.0.0.1:9090/-/ready\n"
            "  tags:\n"
            "    - monitoring\n",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)
        run_history = RunHistory(prompt="what is running?")
        token = set_active_run_history(run_history)

        try:
            service_list()
        finally:
            reset_active_run_history(token)

        assert run_history.session.events[-1].kind == "service_list_read"


class TestServiceGet:
    def test_service_get_returns_full_entry(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        registry_path = tmp_path / "services" / "registry.yaml"
        registry_path.parent.mkdir(parents=True)
        registry_path.write_text(
            "- name: nginx\n"
            "  description: Kubernetes nginx workload exposed through a NodePort service.\n"
            "  runtime: kubernetes\n"
            "  location: default\n"
            "  status: expected\n"
            "  managed_by: helm/charts/nginx\n"
            "  endpoints:\n"
            "    - name: http\n"
            "      host: 192.168.1.10\n"
            "      port: 30080\n"
            "      protocol: http\n"
            "  tags:\n"
            "    - kubernetes\n"
            "    - web\n",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)

        assert service_get("nginx") == {
            "name": "nginx",
            "description": "Kubernetes nginx workload exposed through a NodePort service.",
            "runtime": "kubernetes",
            "location": "default",
            "status": "expected",
            "managed_by": "helm/charts/nginx",
            "endpoints": [
                {
                    "name": "http",
                    "host": "192.168.1.10",
                    "port": 30080,
                    "protocol": "http",
                }
            ],
            "tags": ["kubernetes", "web"],
        }

    def test_service_get_rejects_unknown_name(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        registry_path = tmp_path / "services" / "registry.yaml"
        registry_path.parent.mkdir(parents=True)
        registry_path.write_text("[]\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        with pytest.raises(ValueError, match="not in the registry"):
            service_get("grafana")

    def test_service_get_records_run_history(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        registry_path = tmp_path / "services" / "registry.yaml"
        registry_path.parent.mkdir(parents=True)
        registry_path.write_text(
            "- name: grafana\n"
            "  description: Control-node Grafana instance for dashboards.\n"
            "  runtime: systemd\n"
            "  location: control\n"
            "  status: expected\n"
            "  managed_by: ansible/playbooks/install-grafana.yaml\n"
            "  endpoints:\n"
            "    - name: health\n"
            "      url: http://127.0.0.1:3000/api/health\n"
            "  tags:\n"
            "    - monitoring\n",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)
        run_history = RunHistory(prompt="where does grafana live?")
        token = set_active_run_history(run_history)

        try:
            service_get("grafana")
        finally:
            reset_active_run_history(token)

        assert run_history.session.events[-1].kind == "service_detail_read"


class TestServiceUpsert:
    def test_service_upsert_creates_new_entry(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.chdir(tmp_path)

        result = service_upsert(
            name="grafana",
            description="Control-node Grafana instance for dashboards.",
            runtime="systemd",
            location="control",
            status="expected",
            managed_by="ansible/playbooks/install-grafana.yaml",
            endpoints=[
                {
                    "name": "health",
                    "url": "http://127.0.0.1:3000/api/health",
                    "protocol": "http",
                    "scope": "control-node-local",
                }
            ],
            tags=["monitoring", "dashboards"],
        )

        assert result == {
            "path": "services/registry.yaml",
            "action": "created",
            "service": {
                "name": "grafana",
                "description": "Control-node Grafana instance for dashboards.",
                "runtime": "systemd",
                "location": "control",
                "status": "expected",
                "managed_by": "ansible/playbooks/install-grafana.yaml",
                "endpoints": [
                    {
                        "name": "health",
                        "url": "http://127.0.0.1:3000/api/health",
                        "protocol": "http",
                        "scope": "control-node-local",
                    }
                ],
                "tags": ["monitoring", "dashboards"],
            },
        }
        assert service_get("grafana") == result["service"]

    def test_service_upsert_updates_existing_entry(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        registry_path = tmp_path / "services" / "registry.yaml"
        registry_path.parent.mkdir(parents=True)
        registry_path.write_text(
            "- name: grafana\n"
            "  description: Old description.\n"
            "  runtime: systemd\n"
            "  location: control\n"
            "  status: expected\n"
            "  managed_by: ansible/playbooks/install-grafana.yaml\n"
            "  endpoints:\n"
            "    - name: health\n"
            "      url: http://127.0.0.1:3000/api/health\n"
            "  tags:\n"
            "    - monitoring\n",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)

        result = service_upsert(
            name="grafana",
            description="Updated description.",
            runtime="systemd",
            location="control",
            status="expected",
            managed_by="ansible/playbooks/install-grafana.yaml",
            endpoints=[
                {
                    "name": "health",
                    "url": "http://127.0.0.1:3000/api/health",
                }
            ],
            tags=["monitoring", "dashboards"],
        )

        assert result["action"] == "updated"
        assert service_get("grafana")["description"] == "Updated description."
        assert service_get("grafana")["tags"] == ["monitoring", "dashboards"]

    def test_service_upsert_rejects_invalid_endpoint_shape(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.chdir(tmp_path)

        with pytest.raises(ValueError, match="either `url` or both `host` and `port`"):
            service_upsert(
                name="nginx",
                description="Kubernetes nginx service.",
                runtime="kubernetes",
                location="default",
                status="expected",
                managed_by="helm/charts/nginx",
                endpoints=[
                    {
                        "name": "http",
                        "protocol": "http",
                    }
                ],
                tags=["web"],
            )

    def test_service_upsert_records_run_history(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.chdir(tmp_path)
        run_history = RunHistory(prompt="track grafana in the registry")
        token = set_active_run_history(run_history)

        try:
            service_upsert(
                name="grafana",
                description="Control-node Grafana instance for dashboards.",
                runtime="systemd",
                location="control",
                status="expected",
                managed_by="ansible/playbooks/install-grafana.yaml",
                endpoints=[
                    {
                        "name": "health",
                        "url": "http://127.0.0.1:3000/api/health",
                    }
                ],
                tags=["monitoring"],
            )
        finally:
            reset_active_run_history(token)

        assert run_history.session.events[-1].kind == "service_registry_write"
