# ADR-0017: Multi-Agent Collaboration Mesh (A2A Protocol & Mesh)

- **Status**: Approved
- **Date**: 2026-09-02
- **Author**: Core AI Team (`irsalshydiq <ichalprov@gmail.com>`)
- **Review Phase**: Phase 7 / Level 4 Milestone

---

## 1. Context

Sebelumnya pada arsitektur runtime NexusAI, eksekusi dipusatkan pada satu agen monolitik (*single-agent turn loop*) atau delegasi sub-task secara langsung ke penjadwal terdistribusi (`DistributedExecutionScheduler`).

Namun, tugas rekayasa perangkat lunak modern (seperti arsitektur refactoring, audit keamanan, dan penulisan kode kritis) menuntut segregasi tanggung jawab (*Separation of Concerns*) dan proses negosiasi multi-agen:
1. **Kurangnya Pengawasan Silang (Lack of Cross-Auditing)**: Agen perancang kode (*coder*) sering kali bias terhadap keputusannya sendiri jika tidak ada agen pengawas (*critic/auditor*) independen yang mengevaluasi kepatuhan arsitektur, keamanan, dan fungsionalitas.
2. **Ketiadaan Protokol Pesan Terstandarisasi Antar-Agen**: Belum ada abstraksi envelope pesan A2A (*Agent-to-Agent*) yang terstruktur untuk mengomunikasikan delegasi tugas, proposal solusi, umpan balik revisi, dan konsensus akhir.
3. **Risiko Deadlock / Infinite Reasoning**: Tanpa batas iterasi dan protokol negosiasi yang jelas, interaksi antar agen berisiko mengalami kebuntuan (*infinite revision loops*).

---

## 2. Decision

Kami memutuskan untuk mengimplementasikan **Multi-Agent Collaboration Mesh (A2A Protocol & Mesh)** di dalam paket `nexusai.brain.domain.collaboration` dan `nexusai.brain.runtime.collaboration`:

1. **Envelope Komunikasi Terstandarisasi (`A2AMessage`)**:
   - Setiap pesan antar-agen dienkapsulasi dengan atribut: `message_id`, `sender_id`, `sender_role`, `recipient_id` (mendukung point-to-point ID atau wildcard `'*'`), `message_type`, `conversation_id`, `payload`, dan `timestamp`.
   - Tipe pesan didasarkan pada taksonomi semantik: `TASK_DELEGATION`, `PROPOSAL`, `REVIEW_FEEDBACK`, `CONSENSUS_REACHED`, dan `BROADCAST`.

2. **Perutean Pesan Terdistribusi (`AgentCollaborationMesh`)**:
   - Mesh menyediakan antrean mailbox asinkron (`asyncio.Queue`) per agen yang terdaftar.
   - Mendukung perutean langsung (*point-to-point*) maupun pengumuman menyeluruh (*broadcast*) serta pelacakan riwayat kronologis per percakapan (`conversation_id`).

3. **Spesialisasi Peran Agen (`AgentRole` & Specialist Classes)**:
   - **`PlannerSpecialist`**: Menganalisis tujuan pengguna dan menghasilkan dekomposisi rencana terstruktur serta batasan arsitektur.
   - **`CoderSpecialist`**: Mengimplementasikan artefak kode teknis dan merespons poin-poin kritik pada putaran berikutnya.
   - **`AuditorSpecialist`**: Mengevaluasi proposal kode secara independen berdasarkan kriteria keamanan dan aturan arsitektur, menerbitkan vonis `APPROVED` atau `CHANGES_REQUESTED`.
   - **`OrchestratorSpecialist`**: Mengorkestrasi siklus hidup negosiasi multi-turn, menegakkan batas maksimum putaran (`max_rounds`), dan mengumumkan konsensus akhir klaster.

---

## 3. Alternatives Considered

1. **Shared Blackboard Memory Tanpa Message Passing Langsung**:
   - *Ditolak*: Menimbulkan *race conditions* pada state global dan mempersulit pelacakan alur dialog kausal (*causal dialogue tracking*) antar agen.
2. **Framework Eksternal (seperti AutoGen / CrewAI)**:
   - *Ditolak*: Menambahkan dependensi eksternal berat yang merusak prinsip *zero-amnesia*, determinisme, dan *DAG import isolation* NexusAI.

---

## 4. Consequences

### Positive Consequences
- **Peningkatan Kualitas Kode & Keamanan**: Adanya peran independen `AuditorSpecialist` memastikan setiap output kode diinspeksi sebelum dideklarasikan selesai.
- **Transparansi Jejak Keputusan (Audit Trail)**: Seluruh riwayat percakapan dan negosiasi tersimpan secara kronologis dalam `CollaborationResult.dialogue_history`.
- **Ketahanan Terhadap Deadlock**: Batas `max_rounds` menjamin loop negosiasi selalu selesai (*bounded execution*).

### Negative Consequences
- Overhead waktu inferensi sedikit bertambah karena adanya tahapan review terpisah antara Coder dan Auditor.

---

## 5. Validation Criteria

1. **Message Routing Verification**:
   - Pengujian pengiriman point-to-point dan broadcast melalui `AgentCollaborationMesh`.
2. **Consensus Negotiation Verification**:
   - Verifikasi alur sukses di mana Auditor menyetujui proposal Coder dan Orchestrator menghasilkan `CONSENSUS_APPROVED`.
3. **Iterative Revision Verification**:
   - Verifikasi alur penolakan di mana Auditor meminta perbaikan dan Coder merevisi kode pada iterasi berikutnya hingga lolos.
4. **Max Rounds Cutoff Guard**:
   - Verifikasi bila Auditor terus menolak melebihi `max_rounds`, Orchestrator mengakhiri loop dengan aman bertanda `MAX_ROUNDS_EXCEEDED`.

---

## 6. Review Phase

- Milestone: Phase 7 / Level 4 Milestone
- Target Rilis: v1.0.0-rc1 / v1.0.0 Final
