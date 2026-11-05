# Article Research & SEO Analyzer

Aplikasi Streamlit gratis untuk mengekstrak artikel publik dari URL, melakukan pemeriksaan SEO dasar, menampilkan gambar sumber, dan menyiapkan brief Rewriter.

## Fitur

- Ekstraksi judul, meta description, canonical URL, heading, isi artikel, dan tautan.
- Deteksi gambar utama dari Open Graph, Twitter Card, dan metadata JSON-LD.
- Ekstraksi gambar dalam kontainer artikel, termasuk lazy-loaded image dan srcset jika tersedia.
- Preview gambar sumber beserta URL, alt text, caption, dan kredit jika terdeteksi.
- Pemeriksaan SEO on-page, perkiraan search intent, frekuensi kata, dan rekomendasi.
- Inventaris gambar dapat diunduh sebagai JSON.
- Brief Rewriter menggabungkan teks artikel, keyword, rekomendasi SEO, serta inventaris gambar agar proses penulisan ulang dapat mempertimbangkan gambar sumber.
- Laporan Full Analysis dapat diunduh sebagai TXT.

## Menjalankan lokal

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy publik

1. Buka https://share.streamlit.io/ dan masuk dengan GitHub.
2. Pilih repository `muflihulfata/article-research-seo-analyzer`.
3. Pilih branch `main`, file utama `app.py`, lalu Deploy.
4. Pastikan aplikasi disetel Public agar dapat dibuka pengunjung tanpa login.

## Batasan penting

- Tidak membutuhkan API berbayar atau kunci API.
- Rewriter pada versi ini menghasilkan brief/prompt berbasis hasil analisis dan data gambar; pembuatan artikel oleh model AI belum berjalan otomatis di dalam aplikasi.
- Situs dapat memblokir scraping, hotlink, JavaScript, atau akses otomatis; hasil teks dan gambar mungkin tidak lengkap.
- URL gambar yang berhasil diekstrak tidak otomatis berarti gambar bebas digunakan ulang. Periksa lisensi, izin, dan kewajiban atribusi sebelum publikasi.
- Search intent, frekuensi keyword, dan skor merupakan estimasi heuristik, bukan data resmi Google. Aplikasi tidak mengambil volume pencarian, ranking Google, backlink, atau data Search Console.
- Hosting gratis memiliki batas pemakaian dan dapat berubah.
