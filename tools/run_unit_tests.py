"""
Workspace Unit Test Runner Script.
"""

import asyncio
import os
import sys
from pathlib import Path
import unittest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

from tests.kernel.test_service_and_transaction import (
    test_async_transaction_context_manager_commit,
    test_async_transaction_context_manager_rollback,
    test_kernel_service_lifecycle_and_probes,
)
from tests.memory.integration.test_acceptance_memory_engine import (
    test_memory_engine_public_api_acceptance,
)
from tests.memory.integration.test_end_to_end_concurrency_and_benchmarks import (
    test_concurrent_stress_operations,
    test_end_to_end_memory_lifecycle,
    test_model_specific_formatters,
)
from tests.memory.integration.test_resilience_and_degraded_acceptance import (
    test_outbox_dlq_resilience_routing,
    test_resilience_degraded_health_mode,
)
from tests.memory.integration.test_sla_regression_benchmarks import (
    test_sla_latency_regression_benchmarks,
)
from tests.memory.unit.test_contracts import (
    test_embedding_capabilities_value_object,
    test_memory_exception_hierarchy,
    test_memory_record_creation_defaults,
    test_retrieval_context_defaults,
)
from tests.memory.unit.test_milestone_2_4_2 import (
    test_domain_aggregate_invariants,
    test_json_outbox_serializer,
    test_memory_service_full_flow,
)
from tests.memory.unit.test_milestone_2_4_3 import (
    test_file_storage_compliance,
    test_in_memory_storage_compliance,
    test_pipeline_factory_profiles,
    test_sqlite_storage_compliance,
    test_versioned_json_outbox_serializer,
)
from tests.memory.unit.test_milestone_2_4_4 import (
    test_json_memory_serializer,
    test_local_embedding_provider_compliance,
    test_mock_embedding_provider_compliance,
    test_remote_embedding_provider_compliance,
)
from tests.memory.unit.test_milestone_2_4_5 import (
    test_chroma_vector_store_compliance,
    test_in_memory_vector_compliance,
    test_mock_vector_store_compliance,
)
from tests.memory.unit.test_milestone_2_4_6 import (
    test_context_builder_formatting,
    test_retrieval_engine_middleware_stages,
)
from tests.memory.unit.test_milestone_2_4_7 import (
    test_context_builder_strategies,
    test_pipeline_trace_telemetry,
    test_policy_engine_retention,
)
from tests.memory.unit.test_milestone_2_4_8 import (
    test_deduplication_policy,
    test_domain_vs_integration_events,
    test_pipeline_trace_exports,
    test_prompt_formatters,
)


class TestKernelAndMemory(unittest.TestCase):
    def test_kernel_service(self):
        asyncio.run(test_kernel_service_lifecycle_and_probes())

    def test_async_transaction_commit(self):
        asyncio.run(test_async_transaction_context_manager_commit())

    def test_async_transaction_rollback(self):
        asyncio.run(test_async_transaction_context_manager_rollback())

    def test_memory_record(self):
        test_memory_record_creation_defaults()

    def test_embedding_caps(self):
        test_embedding_capabilities_value_object()

    def test_retrieval_context(self):
        test_retrieval_context_defaults()

    def test_memory_exception(self):
        test_memory_exception_hierarchy()

    def test_domain_aggregate_invariants(self):
        test_domain_aggregate_invariants()

    def test_json_outbox(self):
        test_json_outbox_serializer()

    def test_memory_service_flow(self):
        asyncio.run(test_memory_service_full_flow())

    def test_in_memory_storage_compliance(self):
        asyncio.run(test_in_memory_storage_compliance())

    def test_file_storage_compliance(self):
        asyncio.run(test_file_storage_compliance())

    def test_sqlite_storage_compliance(self):
        asyncio.run(test_sqlite_storage_compliance())

    def test_pipeline_factory_profiles(self):
        test_pipeline_factory_profiles()

    def test_versioned_json_outbox_serializer(self):
        test_versioned_json_outbox_serializer()

    def test_mock_embedding_compliance(self):
        asyncio.run(test_mock_embedding_provider_compliance())

    def test_local_embedding_compliance(self):
        asyncio.run(test_local_embedding_provider_compliance())

    def test_remote_embedding_compliance(self):
        asyncio.run(test_remote_embedding_provider_compliance())

    def test_json_memory_serializer(self):
        test_json_memory_serializer()

    def test_in_memory_vector_compliance(self):
        asyncio.run(test_in_memory_vector_compliance())

    def test_mock_vector_store_compliance(self):
        asyncio.run(test_mock_vector_store_compliance())

    def test_chroma_vector_store_compliance(self):
        asyncio.run(test_chroma_vector_store_compliance())

    def test_retrieval_engine_middleware_stages(self):
        asyncio.run(test_retrieval_engine_middleware_stages())

    def test_context_builder_formatting(self):
        test_context_builder_formatting()

    def test_pipeline_trace_telemetry(self):
        asyncio.run(test_pipeline_trace_telemetry())

    def test_context_builder_strategies(self):
        test_context_builder_strategies()

    def test_policy_engine_retention(self):
        asyncio.run(test_policy_engine_retention())

    def test_domain_vs_integration_events(self):
        test_domain_vs_integration_events()

    def test_pipeline_trace_exports(self):
        test_pipeline_trace_exports()

    def test_prompt_formatters(self):
        test_prompt_formatters()

    def test_deduplication_policy(self):
        asyncio.run(test_deduplication_policy())

    def test_end_to_end_memory_lifecycle(self):
        asyncio.run(test_end_to_end_memory_lifecycle())

    def test_concurrent_stress_operations(self):
        asyncio.run(test_concurrent_stress_operations())

    def test_model_specific_formatters(self):
        test_model_specific_formatters()

    def test_memory_engine_public_api_acceptance(self):
        asyncio.run(test_memory_engine_public_api_acceptance())

    def test_sla_latency_regression_benchmarks(self):
        asyncio.run(test_sla_latency_regression_benchmarks())

    def test_resilience_degraded_health_mode(self):
        asyncio.run(test_resilience_degraded_health_mode())

    def test_outbox_dlq_resilience_routing(self):
        asyncio.run(test_outbox_dlq_resilience_routing())


if __name__ == "__main__":
    unittest.main()
