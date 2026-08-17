# Video Downloader

Web downloader berbasis [yt-dlp](https://github.com/yt-dlp/yt-dlp), dibuat untuk
keperluan pribadi dan tugas kuliah.

Arsitekturnya asinkron: request HTTP hanya memasukkan job ke antrean dan langsung
kembali, sementara worker terpisah menjalankan yt-dlp. Ini penting — download bisa
memakan beberapa menit, dan kalau dijalankan langsung di dalam request, koneksi akan
timeout dan server tumbang begitu ada beberapa user bersamaan.

```
Browser ──POST /api/jobs──► FastAPI ──► Redis (antrean) ──► Worker ──► yt-dlp + ffmpeg
   │                            │                              │
   └──GET /api/jobs/{id}────────┘◄────── status & progress ─────┘
   └──GET /api/jobs/{id}/file──► file hasil (dihapus otomatis setelah TTL)
```

## Menjalankan

### Docker (disarankan)

Cara ini sudah termasuk ffmpeg, Redis, worker, dan pembersih file otomatis.

```bash
cp .env.example .env
docker compose up --build
```

Buka http://localhost:8000

Untuk menaikkan jumlah download bersamaan (1 worker = 1 download):

```bash
docker compose up --scale worker=3
```

### Manual

Butuh **ffmpeg** dan **Redis** terpasang di sistem.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

redis-server &                              # terminal 1
uvicorn app.main:app --reload               # terminal 2
python worker.py                            # terminal 3
python cleanup.py                           # terminal 4
```

> **ffmpeg wajib, bukan opsional.** YouTube menyajikan video dan audio sebagai
> stream terpisah (DASH). Tanpa ffmpeg, resolusi maksimal yang bisa diambil hanya
> 360p, dan preset `audio_mp3` tidak akan jalan sama sekali.

## API

| Method | Endpoint | Keterangan |
| --- | --- | --- |
| `GET` | `/api/presets` | Daftar pilihan kualitas |
| `POST` | `/api/probe` | Metadata video (judul, durasi, thumbnail), tanpa mengunduh |
| `POST` | `/api/jobs` | Masukkan job ke antrean → `202` + `job_id` |
| `GET` | `/api/jobs/{id}` | Status & progress |
| `GET` | `/api/jobs/{id}/file` | Unduh hasilnya |
| `GET` | `/healthz` | Health check |

Dokumentasi interaktif tersedia di `/api/docs`.

```bash
curl -X POST localhost:8000/api/jobs \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://youtu.be/xxxx","preset":"720p"}'
```

## Keputusan keamanan

Ini bagian yang paling sering bikin server downloader dibajak. Yang sudah
diterapkan di sini:

- **Tidak ada `exec()` / shell.** yt-dlp dipakai lewat API Python (`app/tasks.py`),
  jadi tidak ada string perintah yang bisa disisipi input user.
- **User tidak pernah mengirim opsi yt-dlp.** Yang boleh dipilih hanya id preset
  dari `app/formats.py`. Opsi seperti `--exec`, `-o`, atau `--config-location`
  bisa dipakai menjalankan perintah arbitrer di server, jadi string format yt-dlp
  yang sebenarnya tidak pernah keluar-masuk lewat HTTP.
- **Allowlist domain + tolak IP literal** (`app/validators.py`). Tanpa ini, user
  bisa mengirim `file:///etc/passwd` atau `http://169.254.169.254/` untuk membaca
  kredensial dari endpoint metadata cloud.
- **Nama file disanitasi** (`restrictfilenames`), file disimpan di folder per-job
  ber-UUID, dan path hasil di-resolve lalu dicek masih berada di dalam folder job
  sebelum dikirim.
- **Pesan error dibersihkan.** Output mentah yt-dlp bisa membocorkan path server
  dan konfigurasi proxy, jadi yang sampai ke browser hanya pesan umum; detail
  teknis tetap masuk log worker.
- **Rate limit per IP** dan batas durasi/ukuran/timeout job.
- **Container tidak berjalan sebagai root.**

Di belakang reverse proxy, jalankan uvicorn dengan `--proxy-headers` dan
`--forwarded-allow-ips=<ip-proxy>`, kalau tidak rate limit akan menghitung semua
user sebagai satu IP. Jangan membaca `X-Forwarded-For` langsung — klien bisa
memalsukannya.

## Batas & kuota

Semuanya diatur lewat `.env`:

| Setting | Default | Fungsi |
| --- | --- | --- |
| `FILE_TTL_SECONDS` | 7200 | Umur file sebelum dihapus otomatis |
| `MAX_DURATION_SECONDS` | 3600 | Video lebih panjang ditolak |
| `MAX_FILESIZE_MB` | 1024 | Batas ukuran unduhan |
| `JOB_TIMEOUT_SECONDS` | 900 | Job yang macet dibunuh |
| `MIN_FREE_DISK_MB` | 2048 | Job ditolak kalau disk hampir penuh |
| `RATE_LIMIT_REQUESTS` | 10 | Request per IP per window |

`cleanup.py` menyapu folder kedaluwarsa tiap 5 menit. Jangan matikan proses ini —
tanpa dia, disk akan penuh dalam hitungan hari.

## Kalau kena "Sign in to confirm you're not a bot"

Ini masalah paling umum saat deploy, dan **bukan bug di kode ini**. Di localhost
semuanya lancar; begitu dipasang di VPS, YouTube memblokir karena IP datacenter.
Opsinya, semua ada tradeoff-nya:

1. **Jalankan di koneksi rumah** — IP residensial, paling aman untuk tugas kuliah,
   tapi tidak bisa diskalakan.
2. **Cookies akun** — set `COOKIES_FILE` di `.env` ke file format Netscape hasil
   ekspor. Pakai akun sekali-pakai, jangan akun utama: akun bisa kena limit atau
   banned. Jangan pernah commit file cookies (sudah masuk `.gitignore`).
3. **Residential proxy** — set `PROXY`. Ini yang dipakai layanan komersial, dan
   berbayar.

Kalau extractor tiba-tiba rusak padahal sebelumnya jalan, biasanya karena situs
sumbernya berubah. Update dulu sebelum menduga kodenya bermasalah:

```bash
pip install -U yt-dlp
```

Versi yt-dlp sengaja tidak dipin ke versi persis di `requirements.txt` — perbaikan
extractor hanya datang lewat rilis baru.

## Testing

```bash
pip install -r requirements-dev.txt
pytest
```

Test fokus ke logika validasi (`tests/test_validators.py`) dan penguncian preset
(`tests/test_formats.py`) — dua tempat di mana bug berarti lubang keamanan, bukan
sekadar fitur rusak. Test tidak menyentuh jaringan.

## Struktur

```
app/
  config.py       # setting dari .env
  validators.py   # allowlist domain, tolak IP literal & skema non-http
  formats.py      # preset kualitas (satu-satunya sumber string format yt-dlp)
  jobs.py         # status job di Redis
  ratelimit.py    # rate limit fixed-window per IP
  tasks.py        # pekerjaan download yang dijalankan worker
  routes/api.py   # endpoint HTTP
  main.py         # entry point FastAPI
worker.py         # worker RQ
cleanup.py        # penghapus file kedaluwarsa
static/           # frontend
```

## Catatan legal

yt-dlp adalah perangkat lunak open source yang legal, tetapi **mengoperasikan
layanan downloader publik** adalah hal yang berbeda:

- Melanggar Terms of Service YouTube dan sebagian besar platform lain.
- Banyak penyedia hosting melarangnya di AUP — server bisa disuspend tanpa peringatan.
- Beberapa situs downloader besar sudah pernah menghadapi tuntutan hukum,
  terutama yang memasang iklan.

Proyek ini ditujukan untuk penggunaan pribadi: mengunduh konten milik sendiri,
konten berlisensi terbuka, atau arsip pribadi. Kalau mau dipublikasikan, pahami
dulu risikonya.

## Langkah berikutnya

- Ganti polling dengan SSE atau WebSocket untuk progress realtime
- Dukungan playlist (hapus `noplaylist`, batasi jumlah item, kirim sebagai ZIP)
- Captcha kalau dibuka ke publik
- Stream langsung ke klien tanpa menyimpan ke disk (hemat storage, tapi tidak bisa resume)
- Objek storage (S3/MinIO) supaya API dan worker tidak perlu berbagi volume
