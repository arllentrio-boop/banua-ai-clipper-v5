# BANUA AI CLIPPER V6 ULTRA PRO — prototype

## Cara pakai
Unggah seluruh file ke root repository GitHub `banua-ai-clipper-v5` (gantikan file yang lama). Deploy sebagai Docker Web Service pada Render atau server Docker lain. Port mengikuti variabel `PORT`. Akses URL server yang baru untuk menguji langsung. Cloudflare frontend lama tidak otomatis terhubung ke backend baru.

## Fitur
- Registrasi/login akun dengan password PBKDF2 dan sesi 24 jam.
- Upload video maksimum 100 MB; alternatif URL via yt-dlp.
- Pemotongan FFmpeg, rasio 9:16, 1:1, 16:9.
- Whisper tiny transkripsi (unduh model saat pertama kali), subtitle SRT terpisah.
- Pemeringkatan kandidat berdasarkan kepadatan kata dan kata pemicu (heuristik, bukan model prediksi viral terlatih).
- Face-aware crop menggunakan deteksi wajah pada satu frame per klip, **bukan continuous tracking**.
- Judul/caption dibuat dari transkrip (template, **belum AI generatif**).

## Batasan / keamanan
Prototype ini bukan production-ready. Database SQLite, file proyek, dan sesi disimpan pada disk lokal container yang **ephemeral** pada banyak hosting gratis: akun dan hasil dapat hilang saat restart/deploy. Status job disimpan di RAM. Satu proses video dapat menghabiskan CPU/RAM dan gagal pada instance gratis. Download memakai token URL sementara; hindari membagikan URL tersebut. Tambahkan HTTPS, object storage, rate limiting, job queue, antivirus, dan autentikasi yang lebih kuat sebelum membuka pendaftaran publik. Gunakan konten milik sendiri/berizin. Tidak menjamin dukungan semua platform URL.

## Tes
`docker build -t banua-v6 .` lalu `docker run -p 8000:8000 banua-v6` dan buka `http://localhost:8000`.
