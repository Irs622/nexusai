# ADR-0017: Multi-Agent Collaboration Mesh (A2A Protocol & Mesh)

- **Status**: Approved
- **Date**: 2026-09-02
- **Author**: Core AI Team (`irsalshydiq <ichalprov@gmail.com>`)
- **Review Phase**: Phase 7 / Level 4 Milestone

---

## 1. Context

Previously in the NexusAI runtime architecture, execution was centered on a single agent monolithic loop (single-agent turn loop) or direct sub-task delegation to the distributed scheduler (`DistributedExecutionScheduler`).

However, complex engineering tasks (such as architectural refactoring, security audits, and critical code generation) demand strict Separation of Concerns and multi-agent negotiation workflows:
1. **Lack of Cross-Auditing**: A coder agent often exhibits confirmation bias toward its own decisions without an independent critic or auditor agent evaluating architecture compliance, security vulnerabilities, and functionality.
2. **Absence of Standardized Inter-Agent Messaging**: There was no structured Agent-to-Agent (A2A) message envelope abstraction to handle task delegation, proposals, revision feedback, and final consensus.
3. **Deadlock & Infinite Reasoning Risks**: Without explicit iteration boundaries and negotiation protocols, inter-agent collaboration risks falling into infinite revision loops.

---

## 2. Decision

We decided to implement the **Multi-Agent Collaboration Mesh (A2A Protocol & Mesh)** within `nexusai.brain.domain.collaboration` and `nexusai.brain.runtime.collaboration`:

1. **Standardized Communication Envelope (`A2AMessage`)**:
   - Encapsulates every inter-agent communication: `message_id`, `sender_id`, `sender_role`, `recipient_id` (supporting point-to-point IDs or `'*'`), `message_type`, `conversation_id`, `payload`, and `timestamp`.
   - Message types follow a semantic taxonomy: `TASK_DELEGATION`, `PROPOSAL`, `REVIEW_FEEDBACK`, `CONSENSUS_REACHED`, and `BROADCAST`.

2. **Distributed Message Routing (`AgentCollaborationMesh`)**:
   - The mesh provides an asynchronous mailbox queue (`asyncio.Queue`) for each registered agent.
   - Supports both direct point-to-point delivery and full broadcasts, along with chronological history tracking per `conversation_id`.

3. **Specialized Agent Roles (`AgentRole` & Specialist Classes)**:
   - **`PlannerSpecialist`**: Analyzes the user's objective and generates structured plan breakdowns and architectural constraints.
   - **`CoderSpecialist`**: Implements technical code artifacts and addresses critique points in subsequent negotiation rounds.
   - **`AuditorSpecialist`**: Independently evaluates code proposals against security criteria and architectural rules, issuing an `APPROVED` or `CHANGES_REQUESTED` verdict.
   - **`OrchestratorSpecialist`**: Coordinates the multi-turn negotiation lifecycle, enforces maximum turn limits (`max_rounds`), and announces cluster-wide consensus.

---

## 3. Alternatives Considered

1. **Shared Blackboard Memory Without Direct Message Passing**:
   - *Rejected*: Introduces race conditions on global state and impedes causal dialogue tracking across agents.
2. **External Frameworks (e.g., AutoGen / CrewAI)**:
   - *Rejected*: Incurs heavy external dependencies that violate NexusAI's zero-amnesia principles, determinism, and strict DAG import isolation.

---

## 4. Consequences

### Positive Consequences
- **Elevated Code Quality & Security**: Independent `AuditorSpecialist` reviews guarantee code artifacts are strictly inspected before completion.
- **Transparent Decision Trails (Audit Trail)**: Complete conversational histories and negotiation exchanges are permanently preserved in `CollaborationResult.dialogue_history`.
- **Deadlock Resilience**: Strict `max_rounds` limits guarantee bounded execution.

### Negative Consequences
- Slightly higher inference latency due to decoupled review stages between Coder and Auditor.

---

## 5. Validation Criteria

1. **Message Routing Verification**:
   - Point-to-point and broadcast message delivery verified via `AgentCollaborationMesh`.
2. **Consensus Negotiation Verification**:
   - Verification of successful workflows where the Auditor approves the Coder proposal and the Orchestrator outputs `CONSENSUS_APPROVED`.
3. **Iterative Revision Verification**:
   - Verification of rejection flows where the Auditor requests modifications and the Coder revises code until passing.
4. **Max Rounds Cutoff Guard**:
   - When the Auditor repeatedly requests revisions beyond `max_rounds`, the Orchestrator safely terminates with `MAX_ROUNDS_EXCEEDED`.

---

## 6. Review Phase

- Milestone: Phase 7 / Level 4 Milestone
- Target Release: v1.0.0-rc1 / v1.0.0 Final
