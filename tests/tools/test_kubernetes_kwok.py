import json
import subprocess
from pathlib import Path

import pytest

from devops_bot.tools import (
    helm_list_releases,
    helm_status,
    helm_upgrade_install,
    kubectl_get,
    kubectl_rollout_status,
)

pytestmark = pytest.mark.kwok_integration


def _write_fake_chart(chart_path: Path) -> None:
    templates_path = chart_path / "templates"
    templates_path.mkdir(parents=True)
    (chart_path / "Chart.yaml").write_text(
        "apiVersion: v2\n"
        "name: kwok-fake-app\n"
        "description: Test chart for KWOK-backed Kubernetes tool integration.\n"
        "type: application\n"
        "version: 0.1.0\n"
        "appVersion: 1.0.0\n",
        encoding="utf-8",
    )
    (chart_path / "values.yaml").write_text(
        "replicaCount: 1\n",
        encoding="utf-8",
    )
    (templates_path / "deployment.yaml").write_text(
        """apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ .Release.Name }}
  labels:
    app.kubernetes.io/name: {{ .Release.Name }}
spec:
  replicas: {{ .Values.replicaCount }}
  selector:
    matchLabels:
      app.kubernetes.io/name: {{ .Release.Name }}
  template:
    metadata:
      labels:
        app.kubernetes.io/name: {{ .Release.Name }}
    spec:
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
              - matchExpressions:
                  - key: type
                    operator: In
                    values:
                      - kwok
      tolerations:
        - key: kwok.x-k8s.io/node
          operator: Equal
          value: fake
          effect: NoSchedule
      containers:
        - name: fake-container
          image: fake-image
          ports:
            - name: http
              containerPort: 80
""",
        encoding="utf-8",
    )
    (templates_path / "service.yaml").write_text(
        """apiVersion: v1
kind: Service
metadata:
  name: {{ .Release.Name }}
  labels:
    app.kubernetes.io/name: {{ .Release.Name }}
spec:
  selector:
    app.kubernetes.io/name: {{ .Release.Name }}
  ports:
    - name: http
      port: 80
      targetPort: http
""",
        encoding="utf-8",
    )


def test_helm_and_kubectl_tools_round_trip_against_kwok_objects(
    kwok_cluster,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    chart_path = tmp_path / "kwok-fake-app"
    _write_fake_chart(chart_path)
    release = "kwok-fake-app"
    namespace = "kwok-tools-test"
    monkeypatch.setattr("devops_bot.tools.kubernetes.DEFAULT_KUBECONFIG", kwok_cluster.kubeconfig)
    monkeypatch.setattr("builtins.input", lambda _: "y")

    try:
        output = helm_upgrade_install(
            release=release,
            chart=str(chart_path),
            namespace=namespace,
            timeout="60s",
            create_namespace=True,
        )

        assert release in output
        assert "deployed" in output.lower()

        deployments = kubectl_get("deployments", namespace=namespace)
        assert release in deployments

        rollout = kubectl_rollout_status(
            f"deployment/{release}",
            namespace=namespace,
            timeout="60s",
        )
        assert "successfully rolled out" in rollout

        status = json.loads(helm_status(release, namespace=namespace))
        assert status["name"] == release
        assert status["namespace"] == namespace

        releases = json.loads(helm_list_releases(namespace=namespace, all_namespaces=False))
        assert any(item["name"] == release and item["namespace"] == namespace for item in releases)
    finally:
        subprocess.run(
            ["helm", "uninstall", release, "--namespace", namespace],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=kwok_cluster.env,
        )
        subprocess.run(
            ["kubectl", "delete", "namespace", namespace, "--ignore-not-found=true"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=kwok_cluster.env,
        )


def test_kubectl_get_surfaces_real_kwok_api_errors(
    kwok_cluster,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("devops_bot.tools.kubernetes.DEFAULT_KUBECONFIG", kwok_cluster.kubeconfig)

    with pytest.raises(RuntimeError, match='resource type "definitely-not-a-resource"'):
        kubectl_get("definitely-not-a-resource")
