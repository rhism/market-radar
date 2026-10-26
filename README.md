# Market Radar — Windows 10 Desktop Widget

Dashboard desktop Windows dengan auto-refresh dan timestamp quote. Menampilkan data publik market, market read berbasis aturan, headline, serta analisis AI opsional. **Aplikasi tidak melakukan transaksi.**

## Fitur

- **Semua pair IDR INDODAX yang tersedia di katalog API** — daftar dimuat dinamis, bukan watchlist koin hard-coded. Baris diurutkan berdasarkan volume IDR 24 jam jika data volume tersedia.
- **Global markets:** Gold futures, Brent/WTI crude, USD/IDR, S&P 500, Nasdaq Composite, IHSG, VIX, NVIDIA, Apple, Microsoft, serta saham BBCA/BBRI/TLKM.
- **Market read rule-based:** breadth crypto, perubahan BTC, minyak/emas/Nasdaq/VIX, SMA20 dan RSI14 untuk data yang menyediakan histori.
- **Google News RSS** opsional dengan double-click untuk membuka artikel.
- **AI analysis via OpenRouter (opsional)**. Tombol `Ask AI (manual)` hanya mengirim satu snapshot saat ditekan; AI tidak dipanggil otomatis tiap refresh. Default model `openrouter/free`, yaitu router untuk model gratis yang tersedia. Kuota/ketersediaan model gratis dapat berubah.
- Always on top, update manual/otomatis, dan Start with Windows.

## Instalasi

1. Ekstrak folder ke lokasi permanen.
2. Pastikan Python 3.11+ terpasang dari https://www.python.org/downloads/windows/ dan Tkinter tersedia.
3. Klik dua kali `Run_Market_Radar.bat`. Tidak ada paket tambahan yang harus dipasang.
4. AI tidak wajib. Dashboard harga, market read rule-based, dan headline tetap berjalan tanpa API key.

## Mengaktifkan AI (opsional)

1. Buat API key di https://openrouter.ai/settings/keys.
2. Di Market Radar, klik `AI Settings`, masukkan key, dan biarkan model `openrouter/free` kecuali ingin memilih model ID lain.
3. Klik `Save`, lalu `Ask AI (manual)` untuk meminta analisis snapshot.

API key **tidak ditanam di source code atau README**. Di Windows, aplikasi mengenkripsi key menggunakan Windows DPAPI dan menyimpan hasil terenkripsinya di `%APPDATA%\MarketRadar\settings.json`, di luar folder repo. File settings tersebut tidak perlu diunggah ke GitHub. Tombol `Remove saved key` menghapus key terenkripsi yang tersimpan. Jangan menaruh key di source code atau membagikannya lewat chat.

Panggilan AI manual menggunakan kuota akun OpenRouter. Model `openrouter/free` tidak menjamin kapasitas/kecepatan tertentu dan dapat gagal jika kuota atau penyedia model sedang tidak tersedia.

## Sumber data dan refresh

- Kripto: `https://indodax.com/api/pairs` dan `https://indodax.com/api/summaries` dari public API INDODAX. Jika katalog pair sementara gagal, aplikasi mencoba menemukan pair IDR dari summaries.
- Emas, minyak, FX, indeks, dan saham: endpoint chart Yahoo Finance (tidak resmi; dapat berubah/gagal dan quote mungkin tertunda).
- Berita: Google News RSS; hasil dapat tertunda atau tidak tersedia.
- Crypto refresh sekitar 90 detik; market global sekitar 5 menit; RSS sekitar 15 menit. Bursa saham/futures mengikuti jam sesi masing-masing. Kolom quote menunjukkan timestamp jika tersedia.

## Batasan

Market read berbasis aturan dan jawaban AI bisa keliru. Angka dan sumber perlu diverifikasi; tidak ada ramalan bottom yang pasti, sinyal terjamin, atau nasihat finansial personal. Aplikasi hanya membaca data publik, tidak membuka wallet, tidak mengakses akun INDODAX, dan tidak melakukan trading.

## Troubleshooting

- **N/A / data belum tersedia:** klik Update now dan cek koneksi. Data lama yang berhasil bisa tetap tampil jika sumber gagal.
- **AI gagal:** periksa API key, model ID, koneksi, serta kuota/ketersediaan OpenRouter. Dashboard non-AI tetap bekerja.
- **Aplikasi tidak terbuka:** jalankan `Run_Market_Radar_Debug.bat` untuk melihat pesan error; pastikan Python 3.11+ dan Tkinter terpasang.
- **Menonaktifkan auto-start:** matikan `Start with Windows` atau hapus `MarketRadar.vbs` dari `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup`.

## Files

- `market_radar.py` — source aplikasi.
- `Run_Market_Radar.bat` — launcher normal.
- `Run_Market_Radar_Debug.bat` — launcher untuk melihat error.
- `test_market_radar.py` — tes offline; jalankan `python -m unittest -v test_market_radar.py`.


## Preview

![Market Radar desktop preview](market-radar-preview.png)
