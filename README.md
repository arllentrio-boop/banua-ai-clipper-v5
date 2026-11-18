# BANUA AI CLIPPER V5 ULTRA — Web Edition

Aplikasi web berbahasa Indonesia untuk membuat klip MP4 dari URL video yang bisa diakses. **Tidak perlu upload video dari komputer.**

## Jalankan dengan Docker

1. Instal Docker Desktop (Windows/Mac) atau Docker Engine (Linux).
2. Buka terminal di folder ini.
3. Jalankan `docker compose up --build -d`.
4. Buka `http://localhost:8000` di browser.
5. Tempel link video, pilih jumlah/durasi/rasio, lalu proses.

## Publikasikan online

Deploy folder ini pada VPS atau layanan container hosting yang mendukung Docker, FFmpeg, penyimpanan persisten, dan proses cukup panjang. Atur HTTPS/domain melalui reverse proxy. **Belum di-deploy dan belum ada URL publik.** Jangan mengekspos versi demo langsung ke internet tanpa menambahkan autentikasi, rate limit, pembatasan penggunaan sumber daya, penghapusan otomatis file, dan kontrol keamanan URL/SSRF. Gunakan hanya tautan video yang Anda berhak proses.

## Fitur dan batasan

- Sudah dibuat: form link, pengambilan video yt-dlp, auto-cut terdistribusi, 9:16 / 1:1 / 16:9, status proses, preview, download MP4.
- Belum dibuat: penilaian momen viral berbasis AI, subtitle, face tracking, login, billing, dan penjadwalan posting.
- Pemotongan saat ini **berdasarkan sebaran waktu**, bukan AI yang memahami isi video.
- Link privat, DRM, login, batasan platform, atau URL tertentu bisa gagal.
- Job berjalan di thread proses server; tidak tahan restart. Untuk produksi gunakan queue terpisah dan database.
- Video dan hasil klip disimpan pada volume `/data` dan perlu kebijakan penghapusan.
- Batas unduhan yt-dlp adalah 1000 MB, tetapi implementasi ini belum memiliki batas kuota server yang kuat.
