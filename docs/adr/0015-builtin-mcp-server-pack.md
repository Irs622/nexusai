# ADR-0015: Built-in Model Context Protocol (MCP) Server Pack

- **Status**: Approved
- **Date**: 2026-09-01
- **Author**: Core AI Team (`irsalshydiq <ichalprov@gmail.com>`)
- **Review Phase**: Phase 7 / Level 4 Milestone

---

## 1. Context

Sebelumnya pada ADR-0013, NexusAI telah mengintegrasikan **Model Context Protocol (MCP)** dengan client asinkron (`McpClient`), pengelola multi-server (`McpServerManager`), CLI runner (`nexusai mcp`), dan panel dashboard Web OS. Namun, server MCP yang direferensikan dalam konfigurasi contoh (`config/mcp_servers.yaml`) masih mengandalkan runtime eksternal seperti Node.js (`npx @modelcontextprotocol/server-filesystem`) atau package Python terisolasi via `uvx` (`uvx mcp-server-sqlite`).

Ketergantungan pada runtime eksternal tersebut memunculkan beberapa kendala:
1. **Kegagalan di Lingkungan Offline / Air-Gapped**: Eksekusi `npx` atau `uvx` membutuhkan koneksi internet untuk mengunduh paket eksternal saat runtime.
2. **Ketergantungan Eksternal (Node.js)**: Pengguna yang hanya memiliki lingkungan Python murni tidak dapat menggunakan kapabilitas filesystem MCP standar tanpa menginstal Node/NPM.
3. **Ketiadaan Server Bawaan (*Out-of-the-Box*)**: Tidak ada server perkakas dasar (Filesystem, SQLite, Web Fetcher) yang siap jalan secara instan langsung dari repositori NexusAI.

---

## 2. Decision

Kami memutuskan untuk mengimplementasikan **Built-in MCP Server Pack** bawaan NexusAI berbasis Python 3.12+ murni di dalam namespace `nexusai.tools.mcp.servers`:

1. **`McpServerBase` Framework (`nexusai.tools.mcp.servers.base`)**:
   - Abstraksi dasar server Model Context Protocol menggunakan transport standard I/O (stdio JSON-RPC 2.0).
   - Menangani siklus hidup protokol MCP resmi (`2024-11-05`):
     - `initialize`: Negosiasi protokol dan kapabilitas server.
     - `notifications/initialized`: Konfirmasi kesiapan client.
     - `ping`: Health-check latensi stdio.
     - `tools/list`: Mengekspor definisi skema alat (`McpToolDefinition`).
     - `tools/call`: Mengeksekusi handler lokal dan mengembalikan `McpCallToolResult`.
   - Menjamin bahwa seluruh output JSON-RPC dialirkan murni ke `sys.stdout` dengan flushing instan, sementara semua log diagnostik dialihkan ke `sys.stderr`.

2. **Tiga Server MCP Bawaan Spesialis**:
   - **Filesystem Server (`nexusai.tools.mcp.servers.filesystem`)**:
     - Menyediakan alat: `read_file`, `write_file`, `list_directory`, `get_file_info`, `search_files`.
     - **Jail Sandboxing**: Memvalidasi setiap path terhadap direktori root yang ditentukan untuk mencegah eksploitasi *path traversal* (`../`).
   - **SQLite Server (`nexusai.tools.mcp.servers.sqlite`)**:
     - Menyediakan alat: `read_query`, `write_query`, `list_tables`, `describe_table`.
     - Eksekusi asinkron non-blocking menggunakan pustaka `aiosqlite` dengan dukungan parameterized queries.
   - **Web Fetcher Server (`nexusai.tools.mcp.servers.web_fetcher`)**:
     - Menyediakan alat: `fetch_url` (ekstraksi teks/markdown bersih dari HTML tanpa script/style) dan `http_request` (GET/POST/PUT/DELETE generic).
     - Menggunakan `httpx.AsyncClient` dengan timeout terkonfigurasi dan batas ukuran respons.

3. **Konfigurasi Bawaan (`config/mcp_servers.yaml`)**:
   - Mengaktifkan ketiga server bawaan tersebut secara default menggunakan runner modul standar `python3 -m nexusai.tools.mcp.servers.<module>`.

---

## 3. Alternatives Considered

1. **Mempertahankan Ketergantungan Eksternal (npm / npx / uvx)**:
   - *Ditolak*: Menimbulkan latensi startup tinggi saat cold-start, berisiko gagal di container minimalis tanpa Node.js, dan rentan terhadap supply chain attack paket eksternal.
2. **Menjalankan Server sebagai Thread In-Memory (Bukan Subprocess Stdio)**:
   - *Ditolak*: Menyalahi prinsip isolasi proses dan kontrak spesifikasi resmi MCP yang mewajibkan isolasi proses (*process boundary*) via stdio atau SSE.

---

## 4. Consequences

### Positive Consequences
- **Zero-Dependency Setup**: Berjalan langsung menggunakan dependensi yang sudah ada di lingkungan Python NexusAI (`aiosqlite`, `httpx`).
- **Keamanan Sandboxing Terjamin**: Filesystem server menerapkan pembatasan *jail* ketat pada folder root yang diizinkan.
- **Kompatibilitas Penuh**: Server mematuhi spesifikasi JSON-RPC 2.0 MCP resmi sehingga dapat dihubungkan tidak hanya ke NexusAI, tetapi juga ke ekosistem MCP eksternal (Claude Desktop, Cursor, dll).
- **Observabilitas**: Log internal terisolasi ke `sys.stderr`, memastikan aliran stdio JSON-RPC bebas dari polusi teks log.

### Negative Consequences
- Subprocess Python tambahan memakan sedikit jejak memori (~30-40 MB RSS per proses server aktif).

---

## 5. Validation Criteria

1. **Handshake & Protocol Verification**:
   - Seluruh request `initialize`, `ping`, `tools/list`, dan `tools/call` terverifikasi via unit tests `tests/unit/test_mcp_builtin_servers.py`.
2. **Security & Sandboxing Test**:
   - Pengujian path traversal (`../../etc/shadow`) pada `FilesystemMcpServer` wajib ditolak dengan pesan error yang aman.
3. **End-to-End Stdio Subprocess Test**:
   - `McpClient` sukses melakukan spawn subprocess `python3 -m nexusai.tools.mcp.servers.sqlite`, mengeksekusi DDL & DML, dan menutup koneksi tanpa zombie processes.
4. **Static Analysis & Type Compliance**:
   - Lolos 100% `ruff check` dan `mypy --strict`.

---

## 6. Review Phase

- Milestone: Phase 7 / Level 4 Production Hardening
- Target Rilis: v0.8.0 / v1.0.0-rc1
