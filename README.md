# Market Radar — Windows 10 Desktop Widget

Dashboard desktop yang selalu bisa dipasang di atas aplikasi lain, auto-refresh, menampilkan timestamp quote, dan menghasilkan market read berbasis aturan sederhana. **Tidak melakukan transaksi.**

## Yang ditampilkan

- **Crypto/IDR dari INDODAX**: BTC, ETH, SOL, XRP, SUI, QNT, ASTER, NEAR, ALT.
- **Komoditas & pasar global**: Gold futures, Brent, WTI, USD/IDR, S&P 500, Nasdaq Composite, IHSG, VIX, NVIDIA, Apple, Microsoft.
- **Market read sederhana**: breadth kripto, perubahan BTC, pergerakan minyak/emas/Nasdaq/VIX, posisi aset di range 24 jam, SMA20 dan RSI14 untuk data pasar yang menyediakan histori.
- **Headline global** dari Google News RSS (opsional, bergantung jaringan/ketersediaan feed).
- Always on top, update manual, auto-refresh, dan checkbox Start with Windows.

## Instalasi di Windows 10

1. Ekstrak folder ini ke lokasi permanen, misalnya `Documents\Market Radar`.
2. Pastikan Python 3.11+ tersedia: https://www.python.org/downloads/windows/ . Installer resmi Python biasanya menyertakan Tkinter. Aktifkan Python launcher bila ditawarkan.
3. Klik dua kali `Run_Market_Radar.bat`.
4. Tunggu refresh pertama. Internet diperlukan.
5. `Always on top` menjaga panel tetap di depan jendela lain. Aktifkan `Start with Windows` jika ingin dashboard otomatis terbuka saat login Windows. Ini membuat/menghapus file VBS di folder Startup pengguna sendiri.

Aplikasi memakai pustaka standar Python; tidak perlu `pip install`, API key, akun, wallet, atau kredensial exchange.

## Sumber data dan frekuensi

- Kripto: `https://indodax.com/api/summaries` — API publik resmi INDODAX yang didokumentasikan di https://github.com/btcid/indodax-official-api-docs . Auto-refresh sekitar 90 detik.
- Komoditas, FX, indeks, saham: endpoint chart Yahoo Finance (tidak resmi, dapat berubah/gagal dan quote bisa tertunda). Auto-refresh sekitar 5 menit.
- Berita: Google News RSS, sekitar 15 menit. RSS dapat tertunda atau tidak tersedia; buka artikel untuk memeriksa tanggal dan sumber asli.
- Bursa saham dan futures mengikuti jam sesi masing-masing. Akhir pekan sering hanya menampilkan quote sesi Jumat. Kolom Quote time memperlihatkan usia data jika sumber memberikan timestamp.

## Batasan analisis

Market read **bukan ramalan AI dan bukan sinyal trading terjamin**. Watchlist crypto memakai perubahan 24 jam serta posisi harga di low–high 24 jam. SMA20 dan RSI14 dihitung dari histori harian Yahoo. Range 24 jam saja tidak cukup untuk memvalidasi entry; konfirmasi lewat candle timeframe yang relevan dan order book exchange sebelum mengambil keputusan.

Aplikasi tidak membuka wallet, menyimpan API key, melakukan trading, atau menghubungkan akun.

## Troubleshooting

- **N/A atau sumber gagal**: klik Update now, cek internet/firewall/proxy atau status sumber. Data yang berhasil terakhir kali tetap tampil dan status menyebut jika sebagian sumber gagal.
- **Koin tidak tersedia**: pair IDR mungkin tidak ada, sedang maintenance, atau format API berubah. Aplikasi menampilkan N/A, bukan mengarang harga.
- **Aplikasi tidak terbuka**: jalankan `Run_Market_Radar.bat` dari folder dan pastikan Python 3.11+ serta Tkinter tersedia.
- **Hapus auto-start**: matikan `Start with Windows`, atau hapus `MarketRadar.vbs` dari `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup`.

## Files

- `market_radar.py` — source aplikasi.
- `Run_Market_Radar.bat` — Windows launcher.
