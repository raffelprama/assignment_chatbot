# Draft pesan pengumpulan (silakan disesuaikan)

Halo Tim Rekrutmen,

Berikut pengumpulan Technical Assignment AI Engineer: **[tautan repository]**.

**Ringkasan solusi.** PoC AI Assistant untuk SOP berbasis Python, FastAPI, LangGraph/LangChain, Qdrant
(hybrid dense + BM25) dan Gemini. Setiap jawaban menyertakan sitasi dokumen, halaman, nomor bagian dan
kutipan verbatim, dan sitasi tersebut diverifikasi secara deterministik sebelum jawaban ditampilkan.
Pertanyaan yang hanya sebagian didukung dokumen dijawab sebagai `partial` (bagian yang didukung + apa yang
tidak disebutkan dokumen), sedangkan pertanyaan di luar cakupan ditolak dengan template.

**Keputusan teknis utama**
1. Unit retrieval = satu bagian bernomor, dikutip apa adanya. Format Q/A dipakai sebagai *kunci pencarian*
   (beberapa variasi pertanyaan per bagian), bukan sebagai jawaban, agar angka seperti "15 menit" selalu
   dapat ditelusuri ke sumbernya.
2. Ekstraksi dirutekan per halaman berdasarkan kualitas teks: dua PDF ternyata hasil pindai tanpa lapisan
   teks (salah satunya dua kolom) dan dibaca dengan model vision; PDF dua kolom berlapis teks diurutkan
   per kolom berdasarkan koordinat teks. Validator menggagalkan ingesti bila urutan kolom tercampur.
3. Pemeriksaan sitasi deterministik (kutipan harus ada verbatim di bagian yang diambil) adalah lapisan
   keamanan utama; tanpa sitasi valid, tidak ada jawaban yang ditampilkan.

**Hasil evaluasi** (detail di `docs/evaluation.md`): ekstraksi 32/32 bagian dengan CER 0; 37/39 benar
(39/39 tanpa judge) pada set utama dan 12/12 pada set held-out yang ditulis sebelum penyetelan prompt;
0 halusinasi di semua run; ≈ $0,001 per pertanyaan pada harga berbayar.

**Kendala yang ditemui**
- Kuota free tier Gemini: `gemini-2.5-flash` hanya 20 request/hari dan sempat habis; beralih ke
  `gemini-3.5-flash-lite` dengan rantai fallback, rate limiter, dan cache embedding.
- Beban server penyedia (503) membuat latensi bervariasi (p50 6,6–16,8 detik).
- Korpus sangat kecil (4 halaman), sehingga perbandingan strategi retrieval tidak menunjukkan perbedaan
  bermakna; LLM judge juga tidak terbukti memberi manfaat pada korpus ini — keduanya dilaporkan apa adanya.
- Beberapa eksperimen (seluruh KB dalam prompt, top_k 5, uji stabilitas) terhenti karena keterbatasan
  memori mesin; perintah untuk melanjutkannya tersedia di dokumentasi.

Terima kasih.
