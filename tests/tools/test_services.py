from pathlib import Path

import pytest

from devops_bot.history import RunHistory, reset_active_run_history, set_active_run_history
from devops_bot.tools.services import service_list_registry


class TestServiceListRegistry:
    def test_service_list_registry_reads_valid_registry(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        registry_path = tmp_path / "services" / "registry.yaml"
        registry_path.parent.mkdir(parents=True)
        registry_path.write_text(
            "services:\n"
            "  - name: grafana\n"
            "    description: Host-level Grafana service on the control node.\n"
            "    runtime: systemd\n"
            "    location: control\n"
            "    status: expected\n"
            "    managed_by: ansible/playbooks/install-grafana.yaml\n"
            "    endpoints:\n"
            "      - name: health\n"
            "        url: http://127.0.0.1:3000/api/health\n"
            "        protocol: http\n"
            "        scope: control-node-local\n"
            "    tags:\n"
            "      - monitoring\n"
            "      - grafana\n",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)

        assert service_list_registry() == [
            {
                "name": "grafana",
                "description": "Host-level Grafana service on the control node.",
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
                "tags": ["monitoring", "grafana"],
            }
        ]

    def test_service_list_registry_returns_empty_list_when_missing(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.chdir(tmp_path)

        assert service_list_registry() == []

    def test_service_list_registry_rejects_invalid_top_level_shape(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        registry_path = tmp_path / "services" / "registry.yaml"
        registry_path.parent.mkdir(parents=True)
        registry_path.write_text("- name: grafana\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        with pytest.raises(ValueError, match="must be a mapping"):
            service_list_registry()

    def test_service_list_registry_rejects_missing_required_service_fields(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        registry_path = tmp_path / "services" / "registry.yaml"
        registry_path.parent.mkdir(parents=True)
        registry_path.write_text(
            "services:\n  - name: grafana\n    runtime: systemd\n",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)

        with pytest.raises(ValueError, match="Invalid service registry entry"):
            service_list_registry()

    def test_service_list_registry_accepts_host_and_port_endpoint(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        registry_path = tmp_path / "services" / "registry.yaml"
        registry_path.parent.mkdir(parents=True)
        registry_path.write_text(
            "services:\n"
            "  - name: nginx\n"
            "    description: Kubernetes nginx service.\n"
            "    runtime: kubernetes\n"
            "    location: default\n"
            "    status: expected\n"
            "    managed_by: helm/charts/nginx\n"
            "    endpoints:\n"
            "      - name: http\n"
            "        host: 192.168.1.10\n"
            "        port: 30080\n"
            "        protocol: http\n"
            "    tags:\n"
            "      - nginx\n",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)

        registry = service_list_registry()

        assert registry[0]["endpoints"] == [
            {
                "name": "http",
                "host": "192.168.1.10",
                "port": 30080,
                "protocol": "http",
            }
        ]

    def test_service_list_registry_rejects_endpoint_without_url_or_host_port(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        registry_path = tmp_path / "services" / "registry.yaml"
        registry_path.parent.mkdir(parents=True)
        registry_path.write_text(
            "services:\n"
            "  - name: nginx\n"
            "    description: Kubernetes nginx service.\n"
            "    runtime: kubernetes\n"
            "    location: default\n"
            "    status: expected\n"
            "    managed_by: helm/charts/nginx\n"
            "    endpoints:\n"
            "      - name: http\n"
            "        protocol: http\n"
            "    tags:\n"
            "      - nginx\n",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)

        with pytest.raises(ValueError, match="either `url` or both `host` and `port`"):
            service_list_registry()

    def test_service_list_registry_records_run_history(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        registry_path = tmp_path / "services" / "registry.yaml"
        registry_path.parent.mkdir(parents=True)
        registry_path.write_text(
            "services:\n"
            "  - name: prometheus\n"
            "    description: Host-level Prometheus service on the control node.\n"
            "    runtime: systemd\n"
            "    location: control\n"
            "    status: expected\n"
            "    managed_by: ansible/playbooks/install-prometheus.yaml\n"
            "    endpoints:\n"
            "      - name: readiness\n"
            "        url: http://127.0.0.1:9090/-/ready\n"
            "    tags:\n"
            "      - monitoring\n",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)
        run_history = RunHistory(prompt="what is running?")
        token = set_active_run_history(run_history)

        try:
            service_list_registry()
        finally:
            reset_active_run_history(token)

        assert run_history.session.events[-1].kind == "service_registry_read"
