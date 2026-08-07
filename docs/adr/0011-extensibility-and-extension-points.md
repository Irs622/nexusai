# ADR 0011: Framework Extension Points and Plugin Boundaries

* **Status**: ACCEPTED
* **Context**: As NexusAI evolves toward Phase 4 and Phase 5 AI Operating System capabilities (knowledge bases, multi-node agent orchestration, plugin marketplaces), clear extension point boundaries are required to prevent architectural degradation, God Objects, or cross-layer coupling.
* **Decision**:
  1. **Provider Extension Point**: Provider adapters implement `BaseProvider` or `ProviderRuntime` in `nexusai.providers`. `nexusai.brain` interacts strictly via `ProviderSelector` and vendor-neutral `PromptBundle`.
  2. **Strategy Extension Point**: Planning (`IPlanningStrategy`), Reflection (`IReflectionStrategy`), and Decision (`IDecisionStrategy`) strategies implement Protocol contracts in `nexusai.brain.strategy`.
  3. **Context Estimator Extension Point**: `IContextEstimator` protocol allows plugging custom tokenizers or estimators (`CharacterEstimator`, `ProviderTokenizerEstimator`).
  4. **Summarization Extension Point**: `ISummaryGenerator` protocol allows plugging custom summarizers (`StructuredSummaryGenerator`, `LLMSummaryGenerator`).
  5. **Failure Detection Extension Point**: Two-layer architecture (`FailureEvidence` $\rightarrow$ `FailureClassifier`) allows adding new semantic failure categories without modifying detector logic.
  6. **Dependency Container**: `RuntimeDependencies` dataclass container replaces service locators. String-based lookup is strictly forbidden.
* **Alternatives Considered**:
  - *Global Registry / Service Locator*: Rejected to avoid hidden dependencies and runtime string lookup failures.
* **Consequences**:
  - **Positive**: Strict OCP (Open/Closed Principle) enforcement across all framework boundaries.
  - **Positive**: Guaranteed backward compatibility validated by `tests/architecture/test_public_api_contract.py`.
* **Validation Criteria**:
  - `tests/architecture/test_architecture.py`
  - `tests/architecture/test_dependency_graph.py`
  - `tests/architecture/test_public_api_contract.py`
  - `tests/architecture/test_architecture_complexity.py`
* **Review Phase**: Phase 3.3
