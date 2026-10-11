# DEVAM: Build the Builder hackathonu (compact sonrası ilk okunacak dosya)

Son güncelleme: Paz 11 Eki 2026, ~02:00 İstanbul. Yazan: Claude (Opus oturumu), Arda için.

## Zaman
- Gizli brief'ler: **Paz 20:00 İstanbul** (17:00 UTC). Teslim: **Paz 23:00** (20:00 UTC).
- Builder koşusu brief başına en çok 30 dk. Gizli brief'ten koda/prompt'a hiçbir kural, değer, isim yazılmaz (yalnız çökme düzeltmesi).

## Nerede ne var
- Repo: `~/kezo/build-the-builder` · GitHub private `ardaisker/freya-build-the-builder-arda-berk` (remote `origin`) · sunucu klonu `ssh freya-hack` → `/root/hackathon/build-the-builder` (remote `server`, bare `/root/git/btb.git`; sunucuda `git pull`).
- Anahtarlar: `env.sh` (gitignored; `FREYA_API_KEY`, `FREYA_BANK_TEAM_KEY`). Asla yazdırma/commit etme. Sunucuda da var.
- venv: `. .venv/bin/activate` (Python 3.12) → `source env.sh`.
- Freya: staging-app.freyavoice.ai, workspace `09562732-5ca1-41b7-a55f-9f0b2ad175f7`. Aynı anda **tek simülasyon**.
- Geliştirme ajanları (state `.freya-compiled.json`): Brief A ajanı agent `c2bb88f6-4857-4192-a893-e0c73dfde9d8` (workflow `fc564094-...`), A+B ajanı agent `add78035-6e92-4483-83b8-86c3c4f7a0f0` (workflow `d67d500f-...`). Kit örnek ajanı (kontrol): agent `867ee6f5-5f28-4033-b46b-048b4e1b00b4`. Yayınlama: `python3 builder/savetest.py` (out/compiled/*.workflow.json).
- Plan: `~/.claude/plans/nifty-toasting-stonebraker.md`. Takım notu: `TEAM.md`. Mimari: `README-BUILDER.md`.

## Builder (tek komut)
`python3 builder/build.py <brief dosya(lar)ı ya da klasör> <openapi.json> [--slot hidden-1] [--cases public-test-set.json --brief A]`
Akış: extract (Opus, Agent SDK, Max login) → audit (Opus; kanıtlı düzeltmeler) → compile (apimap + kural nesneleri + kod düğümleri) → self-check (yerel) → lint → dry-run → save → smoke → (cases varsa test+patch) → export `submission/<slot>.workflow.json`. İz: `traces/<slot>-<zaman>.log`.
Dosyalar: `builder/{build,extract,compile,apimap,lint,patch,llm,trace,resilient,credits,gate,run_custom,savetest,probe}.py`, `builder/codegen/{calendar_lib,dateparse_lib,facts,resolve_date,tp_resolve,finalize}.py` (kod düğümleri: **süslü parantez yok**, yalnız `vars`), `builder/spec_schema.json`.
Testler: `pytest tests/` (16 test, ağsız). Fixture'lar: `fixtures/` (raw-bank-material, renamed-*, variant-*, edge-cases.json = 42 uç durum, *.spec.json).

## Final koşu (Paz 20:00)
```bash
cd ~/kezo/build-the-builder && . .venv/bin/activate && source env.sh
python3 builder/build.py briefs/hidden-1.md briefs/hidden-1.openapi.json --slot hidden-1 2>&1 | tee traces/hidden-1.log
python3 builder/build.py briefs/hidden-2.md briefs/hidden-2.openapi.json --slot hidden-2 2>&1 | tee traces/hidden-2.log
```
Sonra: `submission/hidden-*.workflow.json` + trace'ler commit + push; `submission/FORM-TEMPLATE.json` doldur (team arda-berk, repo URL, commit, run_command `python3 builder/build.py {brief_path} {tool_api_path}`); **formu Arda gönderir**, repoyu Arda public yapar. Teslim adresi kit e-postasında (bende yok): Arda iletecek. Gizli brief dosyalarını da Arda indirip `briefs/` altına koyacak.
İz dosyasındaki `spec warning` satırlarına bak; self-check "x / x" olmalı.

## Ölçümler (platform sağlıklıyken)
- Regresyon kapısı (Brief A 10 vaka): **10/10 × 3 tekrar** (A v34), sonraki sürümlerde 10/10 × 2 (v35).
- Brief B: **3/3 × 3** (A+B v30).
- 42 uç durum: düz 39-42/42; stiller: in_words 39, corrects 38, asks_back 38, pieces 36, talkative 33 (talkative: platform müşteri cümlelerini kesiyor; kit örneği de 7/10).
- Kit örnek builder'ı (yedek yol, slot `brief-a`): düz 10/10.

## Şu an koşan / sıradaki
- Arka plan kuyruğu (task `blw4172ck`): yeni sürümü yayınlayıp kapı × 2, Brief B × 2, 42 uç durum düz + asks_back/pieces/corrects. Sonuç dosyaları `results/n3-*.log|json`. Compact sonrası ilk iş: bunları oku, düşenleri `freya.get_call(call_id)` ile incele, düzelt.
- Son commit'lerdeki düzeltmeler (henüz ölçülüyor): geri aramada yarım teklif hak tüketmez; "next week + gün"; soru soran müşteri ret sayılmaz; yarım kimlik cevabı araca gönderilmez; zorlukta ret sonrası bir tur bekleme; belirsiz dönem → deadline.
- Öğlene kadar: kod dondurma, sunucuda temiz klon provası (`pytest`, `build.py ... --no-freya --spec fixtures/...`).

## Koşu komutları
- Kapı: `python3 -u builder/gate.py <agent_id> --brief A --reps 3 --out results/x.json` (kit scorer + yeniden deneme + gözcü + kredi koruması)
- Uç durumlar: `python3 -u builder/run_custom.py <agent_id> [--only E01,E02] [--reps 2] [--style in_words|corrects|asks_back|pieces|talkative] --out results/y.json`
- Kredi: `python3 builder/credits.py <çağrı>`; ~0,08 kredi/çağrı; bakiye ~372; **rezerv 100** dokunulmaz.

## Bilinen platform sorunları (bizim hata değil)
- Ajan modeli / API zaman zaman düşüyor (Cmt 16:30-17:10, 22:50-23:04): tüm koşular 0'a iner. Önce kit örnek ajanıyla 1 vaka kontrol et.
- Python sandbox arızası ("Sandbox did not return a parseable result", "snekbox unreachable"): kod düğümleri/hook'lar çalışmaz, çağrı `close_call` ile kapanmaz.
- Mock banka 500 (Cmt 18:35-18:50). Simülasyon "running"de takılabiliyor: `PUT /api/v2/simulations/{id}` `{"status":"completed"}` (gözcü otomatik yapıyor).
- Judge "no verdict" dönebiliyor; ledger doğruysa gürültü.

## Dersler (tekrar etme)
- Arka plan koşularını **öldürme**; sunucu tarafı simülasyon hattı tutar. `python3 -u` kullan (çıktı tamponu). `pgrep -f` ile kendi komutunu eşleştiren bekleyici yazma; süreç numarasına bağlan.
- Kod düğümlerinde değişken adı araç alan adıyla çakışırsa platform alanı "pişirir" (`reason` hatası): iç değişkenler `call_outcome/call_reason`.
- Hızlı chat ucu puanlanan motor değil; karar için simülasyon kullan.
- Her prompt değişikliğinden sonra kapı (10 vaka × 2-3) koş.

## Arda'da bekleyenler
1. Paz 20:00: gizli brief + API dosyalarını `briefs/` altına koy, bana haber ver. 2. Teslim e-posta adresini ilet. 3. Repoyu public yap, formu gönder. 4. İsteğe bağlı: Freya destek kanalına platform kesintilerini bildir.

## 11 Eki 04:40 eki (gece 3)

- Ölçüm (n4): Brief A 10/10 × 5, Brief B 3/3 × 5, 42 uç durum düz 41/42 × 2, in_words 41, asks_back 37, corrects 35, pieces 35.
- Taze okuma provası (n5): builder brief'ten sıfırdan iki ajan üretti (`out/fresh1`, `out/fresh2`; ajanlar f72c8e8c… ve 885e672c…). fresh2: A 10/10 × 3, B 3/3 × 3. fresh1: A'da bir platform takılması, B'de PUB-12 bir koşuda ikinci teklifi atladı (model dalgalanması; kural sıkılaştırıldı).
- Yeni: `notes_backstop` + `backstop_note` düğümleri (çok ürünlü aramada notsuz kalan ürüne kapanıştan önce not). Ders: paralel araç çağrıları `notes_log`/`promises_log` satırlarını ezer; ürün başına işaret kullan (`noted_<id>`, `tried_<id>`). Post-hook isteği göremez; ürün kimliği pre-hook'ta saklanır.
- Geri arama: pencere dışı gün ya da saat tek başına "başarısız öneri" sayılır; "tonight" bugündür.
- Koşan kuyruk: `results/n6-*` (B × 8, A × 3 iki ajanda, uç durumlar düz × 2 + corrects/asks_back/pieces).
- Kredi 04:31'de 334; yedek 100.
