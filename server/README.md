# Server Aktivasi & Langganan POS Retail

Website FastAPI untuk registrasi akun pelanggan, checkout pembayaran,
penerbitan lisensi bertanda tangan Ed25519, dan unduh file `.poslic`.

Alur lengkap ada di `.kilo/webserver_aktivasi.md`.

## Menjalankan

```powershell
# dari root repo (venv yang sama dengan POS)
cp server\.env.example server\.env   # lalu isi konfigurasi
python -m uvicorn server.app.main:app --host 127.0.0.1 --port 8001
```

Database SQLite dibuat otomatis di `server/data/billing.db` saat pertama
jalankan (termasuk seed paket Bulanan/Tahunan/Selamanya).

## Konfigurasi (.env)

| Variabel | Fungsi |
| --- | --- |
| `DATABASE_URL` | Default SQLite; ganti ke PostgreSQL untuk produksi |
| `LICENSE_PRIVATE_KEY_PATH` | Path private key Ed25519 (dipakai POS publisher) |
| `LICENSE_PRIVATE_KEY_PASSPHRASE` | Passphrase private key |
| `MIDTRANS_SERVER_KEY` | Server key sandbox/production Midtrans |
| `MIDTRANS_API_URL` | Default sandbox; ganti ke `https://api.midtrans.com/v2` untuk produksi |
| `ADMIN_API_KEY` | Kunci endpoint `POST /admin/licenses/issue` (hanya pengujian) |

**Private key tidak boleh masuk repository atau file .env.example.**

### Menyiapkan kunci signing

Kunci yang sudah dipakai POS ada di
`%LOCALAPPDATA%\POSPublisher\license-signing-private.pem` (dibuat tool
`scripts/license_publisher.py`). Arahkan `LICENSE_PRIVATE_KEY_PATH` ke file
tersebut, atau buat pasangan baru:

```powershell
python -c "from app.services.license_service import generate_license_keypair; from pathlib import Path; generate_license_keypair(Path('billing-private.pem'), Path('billing-public.pem'), 'kata-sandi-anda')"
```

Jika membuat pasangan baru, ganti juga public key di
`app/core/license_public_key.pem` dan terbitkan ulang lisensi lama.

## Endpoint

### Halaman
- `GET /` — landing + paket
- `GET|POST /register`, `/login` — akun pelanggan (cookie session)
- `GET /dashboard` — unggah `.posreq`, daftar lisensi, pilih paket
- `POST /devices` — registrasi instalasi dari file `.posreq`
- `POST /checkout` — buat order (pending)
- `GET /orders/{kode}` + `POST .../check` — status pembayaran
- `GET /licenses/{id}/download` — unduh `.poslic`

### API JSON
- `POST /api/auth/register`, `/api/auth/login` → `token`
- `GET /api/licenses/me` (cookie `billing_session` atau token via login)
- `POST /api/checkout/create`
- `POST /api/licenses/{id}/renew`, `/api/licenses/{id}/deactivate`
- `POST /webhooks/payment/{provider}` — notifikasi Midtrans (idempoten)
- `POST /admin/licenses/issue` — penerbitan manual (butuh `admin_key`)
- `GET /health`

## Alur pembayaran

1. Pelanggan unggah `.posreq` (berisi `installation_id` + `device_id`) → tabel `devices`.
2. Checkout paket → `orders` (pending) + `licenses` (pending).
3. Midtrans mengirim notifikasi ke `POST /webhooks/payment/midtrans`;
   signature SHA-512 diverifikasi, event ganda diabaikan (idempoten).
4. Saat `settlement` → server menandatangani payload lisensi (Ed25519) dan
   `licenses.status = active`.
5. Pelanggan mengunduh `.poslic` → impor ke POS.

Perpanjangan (`renew`) menambah durasi mulai dari `expires_at` aktif
(bukan dari tanggal bayar), sehingga tidak ada hari yang hilang.

## Perilaku POS setelah lisensi habis

Sisi POS (`main.py` + `app/services/trial_service.py`): trial 7 hari, lalu
setelah masa lisensi/trial habis pengguna bisa memilih **Mode Baca-Saja** —
login tetap bisa, laporan dan ekspor tetap jalan, tetapi transaksi baru
terkunci (checkout, pembelian, pembayaran, pengeluaran; guard di layer service
melempar `LicenseExpiredError` dan tombol Bayar/buka shift/simpan dinonaktifkan).
Impor `.poslic` baru mengembalikan mode normal. Detail di bagian "Trial 7 hari
dan mode baca-saja" pada `README.md`.

## Test

```powershell
python -m pytest tests/test_server_billing.py -q
```

Test memverifikasi langsung bahwa dokumen yang ditandatangani server lolos
`LicenseService.verify_license_file` milik POS.

## Batas keamanan (dari rancangan)

- Tanda tangan mencegah pemalsuan lisensi, tetapi komputer pengguna yang
  sepenuhnya offline tidak dapat dicegah memanipulasi jam sistem; POS
  menyimpan high-water mark waktu lokal untuk trial 7 hari.
- Webhook wajib diverifikasi signature; jangan terbitkan lisensi publik
  tanpa autentikasi.
- Endpoint `admin/licenses/issue` hanya untuk pengembangan — jangan
  diaktifkan di produksi tanpa kontrol akses.
