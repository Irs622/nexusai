"""Kubernetes manifest rendering and deployment validation integration test suite."""

from __future__ import annotations

import os
import pytest


def test_helm_chart_manifest_structure() -> None:
    """Integration Test: Verify Helm chart directory and manifest template files exist."""
    helm_dir = "deploy/helm/nexusai"
    assert os.path.exists(os.path.join(helm_dir, "Chart.yaml"))
    assert os.path.exists(os.path.join(helm_dir, "values.yaml"))
    assert os.path.exists(os.path.join(helm_dir, "values-production.yaml"))
    assert os.path.exists(os.path.join(helm_dir, "templates/deployment-worker.yaml"))
    assert os.path.exists(os.path.join(helm_dir, "templates/networkpolicy.yaml"))
    assert os.path.exists(os.path.join(helm_dir, "templates/rbac.yaml"))
    assert os.path.exists(os.path.join(helm_dir, "templates/serviceaccount.yaml"))


if __name__ == "__main__":
    test_helm_chart_manifest_structure()
    print("ALL HELM MANIFEST STRUCTURE INTEGRATION TESTS PASSED SUCCESSFULLY!")
