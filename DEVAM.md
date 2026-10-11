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

## 11 Eki 08:45: KOD DONDURULDU (commit 6a821ec + bu not)

- Son ölçüm (n8, son sürüm): Brief A 10/10 × 3 (iki ajanda da), Brief B 3/3 × 5, 42 uç durum düz 42/42 × 2, corrects stili 39/42.
- Canlı uçtan uca prova: `build.py briefs/brief-a.md briefs/brief-b.md tools/openapi.json --slot rehearsal` 93 saniyede bitti (okuma, denetim, derleme, kayıt, duman testi, dışa aktarım).
- Sunucuda temiz çekimle: 17 test geçti, çevrimdışı derlemeler tamam.
- Platform notu: 05:52'de bir simülasyon "running" kaldı ve yuvayı iki saat kilitledi; `resilient._clear_stale` artık 25 dakikadan eski takılı simülasyonu kapatıyor. "conversation: no verdict" hakem arızasıdır, ajan kusuru değil.
- Bundan sonra yalnız çökme düzeltmesi. Gizli brief'ten hiçbir kural, değer ya da isim koda yazılmaz.
- Kredi 08:42'de 299; yedek 100.

## 11 Eki 19:30: FİNAL PLANI (onaylı) — önce bunu oku

Plan dosyası: `~/.claude/plans/inherited-swimming-horizon.md` (fazlar, eşikler, ajan rolleri). Özet:

- `main` = Arda + Berk dallarının tamamı (f701037 ve sonrası): güvenlik katmanı, söz engeli, not yedeği, kuralı sözle bırakma (okuma adımı "text" der ya da oracle bir boyutu "ipucu" yapar), oracle adımı, derleme yedeği, bağlantı/504 yeniden denemeleri. 31 test; `builder/golden.py compare out/golden-pre-reveal.json` farksız olmalı.
- Sözler yine mesaj başına bir araçla kaydediliyor (17:05'te ölçülen davranış). Aynı mesajda kaydetme denendi, zor çok ürünlü müşteriyi 12 koşuda 2 kez bozdu, geri alındı.
- Son pratik ölçüm (19:26, birleşme öncesi kod, aynı prompt): Brief B 3/3 × 4, Brief A 10/10. Kuralı sözle bırakılmış ajan Brief A'da 9/10.
- **Açılıştan sonra kural:** yalnız genel hata düzeltmesi; gizli brief'ten koda/prompt'a hiçbir kural, değer, isim yok; elle spec/ajan düzeltmesi yok. Her commit'ten önce `python3 builder/leakcheck.py --base pre-reveal <gizli dosyalar>`.
- **Final komutları:**
  - `python3 builder/finalrun.py --name hidden-1 --runs 3 briefs/<brief1>.md briefs/<api1>.json` (aynısı hidden-2). Tablo: `out/final/<ad>-compare.md`; izler `traces/final-<ad>-r<i>.out` ve `traces/<slot>-<zaman>.log`; ajan dosyaları `submission/<slot>.workflow.json`.
  - Pratik kapı: `python3 -u builder/gate.py add78035-6e92-4483-83b8-86c3c4f7a0f0 --brief B --reps 3` / `--brief A --reps 2` (önce `builder/savetest.py` ile yayınla).
- **Claude eşikleri (haftalık):** %85 Opus alt ajan yok, %90 alt ajan yok, %94 yeniden koşu yok, %98 asla. 19:26'da %68; dört builder koşusu haftalıkta 1 puandan az tuttu. 5 saatlik pencere 19:30'da sıfırlandı.
- Zaman: 20:00 açılış → 20:30 güvenli teslim commit'i → 22:00 kod dondurma → 22:30 son koşular seçildi → 22:45 teslim (Arda: repo public + form).

## 11 Eki 20:35: FİNAL GÖREVİ DEĞİŞTİ (kredi kartı ekstre borcu, Türkçe, kendi mock'umuz)

- Final vakası tahsilat değil: `briefs/final/BRIEF.md`. Paket parça parça geliyor (Drive klasörü
  `1r9KOek3SXiE0mu1wBofezD0bjiAJhcYQ`; 20:35'te yalnız BRIEF.md + akış PDF'i vardı).
- Teslim: Yavuz'un mailine yanıt, 3 ek: `submission.json`, dışa aktarılan workflow, builder izi. 23:00 son.
- Mock: `mock/` (Cloudflare Worker `freya-bank-mock`, adres https://freya-bank-mock.ardaegeisker.workers.dev,
  `cd mock && npx wrangler deploy`). Şu an yankı iskeleti; servis dokümanı gelince gerçek uçlar yazılacak.
- Builder'a ikinci yol eklendi (vaka klasörü): `python3 builder/build.py <klasör> --tool-url <mock adresi>`.
  Dosyalar: `builder/casefolder.py` (her dosyayı okur), `casespec.py` (model: malzeme -> vaka spec'i, denetim, test
  sonucundan düzeltme), `casecompile.py` (spec -> workflow; servis çağrısı kancaları, kodla hesap `derive`, sonuç
  kuralları, kodla kapanış `go`), `casetest.py` (servis kontrolleri + test konuşmaları), `casebuild.py` (akış).
  Eski tahsilat yolu aynen duruyor (tool API dosyasında yedi araç varsa o çalışır).
- Uydurma vaka: `fixtures/case-parcel/` + `fixtures/case-parcel.spec.json`; testler `tests/test_case.py`.
- Koda final vakasından hiçbir şey yazılmaz; mock (`mock/`) vakaya özeldir ve builder'ın parçası değildir.

## 11 Eki 21:32: final koşuları

- Kod donduruldu: `47216b9` (builder) / `c665144` (+README, caseeval). Mock yayında ve 616/616 doğru.
- Paket tam: `briefs/final/` (21:10'da Drive'a eklenen `sources/meetings/2026-10-10-follow-up-session-transcript.txt` dahil;
  dosyalar link ile açık, `curl -L "https://drive.google.com/uc?export=download&id=<id>"` çalışıyor).
- Final adayları: `final-a`, `final-b`, `final-c` (izler `traces/final-<x>-*.log`, çıktı `traces/final-<x>.out`,
  dışa aktarım `submission/final-<x>.workflow.json`, durum `.freya-final-<x>.json`). Komut:
  `python3 builder/build.py briefs/final --tool-url https://freya-bank-mock.ardaegeisker.workers.dev --max-test-rounds 3 --slot final-a`
- Önceki tam klasör koşusu: `final-r5` (eski kod: look-alike ayrımı yok). r4: 11/12.
- Ortak değerlendirme seti: `out/eval/final-eval.json` (alt ajan yazıyor); koşucu:
  `python3 builder/caseeval.py <agent_id> out/eval/final-eval.json --out results/eval-<x>.json`
- Seçim: ortak sette en çok geçen aday. Sonra: `submission/final.workflow.json` + `traces/final.log` kopyala,
  `submission.json` yaz (team arda-berk, repo https://github.com/ardaisker/freya-build-the-builder-arda-berk, commit,
  run_command, mock_url), commit + push; Arda repoyu public yapar ve Yavuz'un mailine 3 ekle yanıt verir (23:00).
- Claude: 21:31'de haftalık %72, 5 saatlik %41. Yeni builder koşusu başlatma (3 final koşusu yeter).
