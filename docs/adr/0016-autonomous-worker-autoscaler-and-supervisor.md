# ADR-0016: Autonomous Worker Auto-Scaler & Heartbeat Supervisor

- **Status**: Approved
- **Date**: 2026-09-02
- **Author**: Core AI Team (`irsalshydiq <ichalprov@gmail.com>`)
- **Review Phase**: Phase 7 / Level 4 Milestone

---

## 1. Context

Pada ADR-0014, NexusAI telah membangun fondasi eksekusi terdistribusi (`nexusai.infrastructure.distributed`) dengan abstraksi node pekerja (`WorkerNode`), pemilihan rute beban (`DistributedWorkerPool`), dan eksekusi konkuren branch PlanGraph DAG (`DistributedExecutionScheduler`) yang berkoordinasi dengan lease `IExecutionCoordinator` dan fencing tokens.

Namun, klaster pekerja tersebut sebelumnya masih bersifat statis:
1. **Ketiadaan Deteksi Node Mati Dinamis**: Bila sebuah worker node mengalami kegagalan proses, partisi jaringan, atau macet (*hang*), status node di pool tidak otomatis terdeteksi sebagai mati (*silent failure*), yang dapat menyebabkan penjadwal terus mencoba mengirim sub-task ke node tersebut.
2. **Ketiadaan Pemulihan Otomatis (*Self-Healing*)**: Tidak ada mekanisme rekonsiliasi yang secara otomatis mengembalikan node ke status `ONLINE` saat layanannya kembali aktif dan sehat.
3. **Kapasitas Statis (*Zero Elasticity*)**: Jumlah node pekerja dalam pool tidak dapat membesar atau mengecil secara dinamis berdasarkan tekanan antrean tugas DAG (*backlog*) atau utilisasi klaster, yang berisiko menyebabkan *head-of-line blocking* saat lonjakan beban atau pemborosan sumber daya saat hening.

---

## 2. Decision

Kami memutuskan untuk mengimplementasikan sistem **Autonomous Worker Auto-Scaler & Heartbeat Supervisor** di dalam paket `nexusai.infrastructure.distributed`:

1. **`WorkerHeartbeatSupervisor` (`supervisor.py`)**:
   - Menjalankan loop latar belakang asinkron (*heartbeat supervision loop*) dengan interval periodik terkonfigurasi (`check_interval_seconds`).
   - Melakukan health ping (`node.ping()`) dan mencatat latensi serta stempel waktu terakhir.
   - **Dead Node Eviction**: Bila suatu node gagal merespons sebanyak $N$ kali berturut-turut (`max_consecutive_failures`, default 3), supervisor otomatis mengubah status node menjadi `OFFLINE`, menghapusnya dari daftar kandidat rute tugas sehat, dan memicu callback `on_node_evicted`.
   - **Auto-Recovery**: Bila node yang berstatus `OFFLINE` atau `DRAINING` kembali merespons ping secara stabil sebanyak `recovery_threshold` (default 2 kali), supervisor otomatis memulihkannya ke status `ONLINE` dan memicu callback `on_node_recovered`.

2. **`WorkerAutoScaler` (`autoscaler.py`)**:
   - Menghitung metrik agregat beban klaster secara real-time (`ClusterMetrics`): utilisasi kapasitas aktif $\frac{\sum \text{active\_tasks}}{\sum \text{capacity}}$ dan jumlah antrean backlog tugas siap jalan.
   - **Scale-Out**: Bila utilisasi $\ge 80\%$ atau antrean backlog tugas $> 0$, otomatis menambahkan node pekerja baru (menggunakan `node_factory`, hingga batas `max_nodes`).
   - **Scale-In**: Bila antrean backlog kosong dan utilisasi $\le 20\%$ setelah periode *cooldown* (default 5 detik), otomatis melakukan *graceful draining* dan menderegistrasi node dinamis yang menganggur (tanpa pernah turun di bawah `min_nodes`).
   - **Anti-Thrashing Guard**: Menerapkan jeda `cooldown_seconds` untuk mencegah osilasi cepat bolak-balik antara penambahan dan penghapusan worker.

3. **`ClusterOrchestrator` (`cluster_manager.py`)**:
   - Bertindak sebagai fasad terpadu yang menggabungkan `DistributedWorkerPool`, `WorkerHeartbeatSupervisor`, dan `WorkerAutoScaler`.
   - Mengelola siklus hidup mulai/berhenti (*lifecycle orchestration*) seluruh background task dan menyediakan snapshot status klaster untuk konsumsi telemetri dashboard Web OS dan Server-Sent Events (SSE).

---

## 3. Alternatives Considered

1. **Mengandalkan Kubernetes HPA (Horizontal Pod Autoscaler) Saja**:
   - *Ditolak*: K8s HPA lambat merespons fluktuasi antrean mikro-DAG (skala detik/milidetik) dan tidak dapat mengatur perutean in-process worker atau container lokal di mesin pengembang.
2. **Polling Reaktif Saat Penjadwalan Saja Tanpa Background Loop**:
   - *Ditolak*: Menimbulkan latensi tambahan (*scheduling overhead*) pada critical path eksekusi DAG dan tidak dapat mendeteksi kegagalan node saat klaster sedang idle.

---

## 4. Consequences

### Positive Consequences
- **Resiliensi Mandiri (Self-Healing)**: Klaster secara otomatis mengisolasi node pekerja yang bermasalah tanpa campur tangan manual operator.
- **Elastisitas Beban Cepat**: Menangani lonjakan beban DAG secara instan melalui penambahan worker dinamis dan memangkas penggunaan sumber daya saat idle.
- **Auditabilitas Telemetri**: Setiap keputusan scaling tercatat dalam `ScalingEvent` terstruktur (`timestamp`, `direction`, `reason`, `nodes_before`, `nodes_after`).
- **Zero Thrashing**: Dilindungi oleh batas jeda cooldown.

### Negative Consequences
- Terdapat overhead CPU/jaringan yang sangat kecil untuk pengiriman paket ping periodik antar worker (terukur $< 0.1\text{ms}$ per round).

---

## 5. Validation Criteria

1. **Heartbeat & Eviction Verification**:
   - Uji node yang gagal merespons ping $3\times$ berturut-turut wajib beralih status ke `OFFLINE` dan ditandai `is_evicted = True`.
2. **Auto-Recovery Verification**:
   - Uji node yang offline namun merespons sukses $2\times$ berturut-turut wajib otomatis kembali menjadi `ONLINE`.
3. **Auto-Scaling Elasticity Verification**:
   - Uji lonjakan backlog memicu `SCALE_OUT` hingga `max_nodes`.
   - Uji kondisi idle memicu `SCALE_IN` hingga `min_nodes` dengan mematuhi cooldown guard.
4. **Clean Concurrency & Zero Leaked Tasks**:
   - Pengujian `ClusterOrchestrator.stop()` wajib mematikan seluruh background tasks tanpa meninggalkan uncollected async tasks.

---

## 6. Review Phase

- Milestone: Phase 7 / Level 4 Production Hardening
- Target Rilis: v0.8.0 / v1.0.0-rc1
