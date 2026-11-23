# Evaluation run: `heldout_v2`

Options: `{"rescored": true}`

## Summary

```json
{
  "questions": 12,
  "correct": 12,
  "by_group": {
    "direct": "6/6",
    "ambiguous": "3/3",
    "unsupported": "2/2",
    "multi": "1/1"
  },
  "failures": {},
  "hallucinations": 0,
  "errors": 0,
  "errors_first_pass": 0,
  "statuses": {
    "answered": 7,
    "partial": 4,
    "out_of_scope": 1
  },
  "judge": {
    "pass": 11,
    "skipped": 1
  },
  "retries": 0,
  "invalid_citations_removed": 0,
  "mean_retrieval_recall": 1.0,
  "latency_ms": {
    "p50": 10726,
    "p95": 54486,
    "max": 111428
  },
  "node_p50_ms": {
    "normalize": 1908,
    "retrieve": 888,
    "answer": 7504,
    "check_citations": 0,
    "judge": 1263,
    "respond": 0
  },
  "llm_calls_per_question": 2.83,
  "tokens_per_question": {
    "input": 1877,
    "output": 237
  },
  "cost_usd_total": 0.01386,
  "cost_usd_per_question": 0.001155,
  "unpriced_calls": 0,
  "models": [
    "gemini-3.5-flash-lite"
  ]
}
```

## Per question

| id | group | status | expected | ok | failure | cited | retrieval recall | ideal | ms |
|---|---|---|---|---|---|---|---|---|---|
| HO1 | direct | answered | answered | ✅ | - | KB_03 §4 | 1.00 | - | 5056 |
| HO2 | direct | answered | answered | ✅ | - | KB_03 §2 | 1.00 | - | 4144 |
| HO3 | direct | answered | answered/partial | ✅ | - | KB_02 §7 | 1.00 | - | 6833 |
| HO4 | ambiguous | partial | partial/answered | ✅ | - | KB_01 §3, KB_04 §2 | 1.00 | - | 44433 |
| HO5 | ambiguous | partial | partial/answered/no_answer | ✅ | - | KB_03 §5 | 1.00 | - | 4695 |
| HO6 | direct | answered | answered | ✅ | - | KB_04 §4 | 1.00 | - | 20923 |
| HO7 | unsupported | out_of_scope | out_of_scope/no_answer | ✅ | - | - | - | - | 2123 |
| HO8 | multi | answered | answered | ✅ | - | KB_04 §1 | 1.00 | - | 26083 |
| HO9 | direct | answered | answered | ✅ | - | KB_03 §7, KB_03 §7 | 1.00 | - | 111428 |
| HO10 | unsupported | partial | partial/no_answer | ✅ | - | KB_04 §2 | 1.00 | - | 10726 |
| HO11 | ambiguous | partial | partial/no_answer | ✅ | - | KB_04 §5 | 1.00 | - | 9159 |
| HO12 | direct | answered | answered/partial | ✅ | - | KB_02 §2 | 1.00 | - | 54486 |

## Answers

**HO1 — Untuk tiket P2, seberapa sering pelanggan harus diberi kabar kalau belum selesai?**  
`answered` · Untuk tiket P2, pelanggan harus diberi kabar setiap 4 jam kerja jika belum selesai [KB_03 §4].

**HO2 — Apa yang harus dicatat saat serah terima shift?**  
`answered` · Saat serah terima shift, petugas harus mencatat tiket aktif, pekerjaan tertunda, hambatan, PIC, dan tenggat pembaruan [KB_03 §2].

**HO3 — Boleh nggak saya janjikan refund ke pelanggan yang komplain?**  
`answered` · Petugas tidak boleh menjanjikan pengembalian dana atau kompensasi sebelum ada persetujuan pejabat berwenang [KB_02 §7].

**HO4 — Is P2 the same as SEV2?**  
`partial` · The documents do not state whether P2 is the same as SEV2. P2 is defined as 'fungsi penting terganggu dengan solusi sementara terbatas' [KB_01 §3], whereas SEV2 is defined as 'layanan utama terdegradasi bagi banyak pengguna' [KB_04 §2].
  
_Not specified:_ Whether P2 and SEV2 are the same.

**HO5 — Bagaimana cara mengubah email akun pelanggan?**  
`partial` · Permintaan perubahan data akun tidak diproses melalui pesan pribadi petugas tanpa verifikasi [KB_03 §5]. Dokumen tidak merinci cara lengkap untuk mengubah email akun pelanggan.
  
_Not specified:_ Dokumen tidak menjelaskan langkah-langkah atau prosedur lengkap untuk mengubah email akun pelanggan.

**HO6 — Siapa yang memimpin komunikasi lintas tim saat insiden?**  
`answered` · Koordinator insiden memimpin keputusan dan komunikasi lintas tim [KB_04 §4].

**HO7 — Berapa gaji petugas layanan?**  
`out_of_scope` · Pertanyaan ini berada di luar cakupan dokumen SOP yang tersedia (Penanganan Tiket Layanan, Pengelolaan Keluhan Pelanggan, Panduan Operasional Layanan, Eskalasi dan Penanganan Insiden). Saya hanya dapat menjawab berdasarkan isi dokumen tersebut.

**HO8 — Apakah setiap keluhan pelanggan otomatis dianggap insiden?**  
`answered` · Tidak, tidak setiap keluhan merupakan insiden karena penilaian didasarkan pada dampak nyata dan risiko [KB_04 §1].

**HO9 — Laporan mingguan berisi apa saja dan dari mana angkanya?**  
`answered` · Laporan mingguan berisi ringkasan jumlah tiket, kategori masalah, ketepatan respons, backlog, dan kendala operasional [KB_03 §7]. Angka-angka tersebut dihitung dari catatan sistem, bukan menggunakan perkiraan manual [KB_03 §7].

**HO10 — Berapa lama SEV4 harus dieskalasi?**  
`partial` · Dokumen menyatakan bahwa SEV4 adalah gangguan minor tanpa dampak signifikan [KB_04 §2], tetapi dokumen tidak menentukan berapa lama SEV4 harus dieskalasi.
  
_Not specified:_ Durasi atau batas waktu eskalasi untuk SEV4.

**HO11 — Kalau insiden SEV2, kapan update status internal harus dibuat?**  
`partial` · Dokumen tidak menyebutkan kapan pembaruan status internal harus dibuat untuk insiden SEV2 [KB_04 §5]. Dokumen hanya menyatakan bahwa untuk SEV1, pembaruan status internal dibuat setiap 20 menit [KB_04 §5].
  
_Not specified:_ Dokumen tidak menentukan jadwal pembaruan status internal untuk insiden SEV2.

**HO12 — Can I attach chat screenshots as complaint evidence?**  
`answered` · Yes, chat screenshots (evidence of conversation) may be attached as long as sensitive data is first masked [KB_02 §2].
