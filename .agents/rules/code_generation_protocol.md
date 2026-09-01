---
description: "Aturan Wajib: AI Agent Wajib Membaca Obsidian Second Brain Sebelum Menulis/Memodifikasi Kode"
applies_to:
  - repository-wide
---

# 🛑 PROTOKOL WAJIB: BACA SECOND BRAIN SEBELUM CODING

Aturan ini bersifat **MANDATORY & NON-NEGOTIABLE** untuk setiap AI Agent (Antigravity, Claude, GPT, dll.) yang bekerja di repositori ini:

---

## 📌 Pemicu (Trigger)
Setiap kali user meminta kode, memberikan tugas coding, refactoring, bugfix, fitur baru, atau modifikasi file (`.py`, `.js`, `.html`, `.css`, `.yaml`, `.sh`, `.toml`, dll.):

---

## 🚫 Yang DILARANG KERAS
1. **Dilarang langsung menulis kode tanpa membaca konteks**.
2. **Dilarang berasumsi atau mengarang arsitektur baru** yang bertentangan dengan keputusan di `vault/Keputusan-Penting.md` atau `vault/ANALISIS-TOTAL-ARSITEKTUR-NEXUSAI.md`.
3. **Dilarang mengabaikan status pengerjaan terakhir** yang tercatat di `vault/Status-Terkini.md`.

---

## ✅ Langkah Wajib Sebelum Menulis Kode (*Pre-Coding Protocol*)
1. **Langkah 1**: Baca `vault/00-Index.md` dan `vault/Status-Terkini.md` untuk mengetahui milestone aktif dan konteks terakhir.
2. **Langkah 2**: Jika tugas berhubungan dengan komponen inti (`brain`, `memory`, `kernel`, `security`, `providers`, `api`, `web`), baca dokumen arsitektur terkait di `vault/Konteks-Proyek.md` atau `vault/ANALISIS-TOTAL-ARSITEKTUR-NEXUSAI.md`.
3. **Langkah 3**: Pastikan kode baru mematuhi aturan Clean Architecture (A001–A019), `mypy --strict`, dan tidak membocorkan kredensial.

---

## 📝 Langkah Wajib Setelah Selesai Coding (*Post-Coding Protocol*)
1. Update checklist atau target di `vault/Status-Terkini.md`.
2. Catat ringkasan file yang diubah dan keputusan teknis di `vault/Log-Sesi/YYYY-MM-DD.md`.
3. Jika ada keputusan arsitektur baru, dokumentasikan di `vault/Keputusan-Penting.md`.
