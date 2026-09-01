---
description: "Aturan memori dan retensi konteks menggunakan Obsidian Second Brain (vault/)"
applies_to:
  - repository-wide
---

# 🧠 Obsidian Second Brain — Context Memory Rule

Aturan ini wajib dipatuhi oleh setiap sesi AI yang bekerja di repositori ini agar **tidak pernah kehilangan konteks**:

---

## 1. Pre-flight (Saat Memulai Sesi / Menerima Instruksi Besar)
- Sebelum mengeksekusi tugas baru atau menjawab pertanyaan seputar kelanjutan proyek, **baca file-file konteks utama**:
  - `vault/00-Index.md` (Map of Content utama)
  - `vault/Status-Terkini.md` (Pekerjaan aktif & target saat ini)
  - `vault/Preferensi-User.md` (Preferensi gaya kerja pengguna)
- Pastikan tidak mengajukan pertanyaan yang jawabannya sudah tercatat di dalam vault.

---

## 2. In-flight (Saat Bekerja)
- Gunakan pedoman arsitektur di `vault/Konteks-Proyek.md`.
- Jika menemukan konflik keputusan, rujuk `vault/Keputusan-Penting.md`.

---

## 3. Post-flight (Setelah Menyelesaikan Pekerjaan Penting)
- Jika ada progres baru, perbarui checklist di `vault/Status-Terkini.md`.
- Jika ada keputusan arsitektur baru atau solusi penting, tambahkan di `vault/Keputusan-Penting.md`.
- Catat ringkasan pekerjaan sesi ini ke dalam `vault/Log-Sesi/YYYY-MM-DD.md` menggunakan format wikilink Obsidian `[[Nama-Catatan]]`.

---

## 4. Format Catatan Obsidian
- Gunakan YAML frontmatter di awal file (`title`, `type`, `updated`, `tags`).
- Hubungkan konsep terkait menggunakan sintaks wikilink `[[Nama-File]]`.
- Gunakan tag seperti `#context`, `#status`, `#decisions`, `#session` agar terpetakan rapi di Graph View Obsidian.
