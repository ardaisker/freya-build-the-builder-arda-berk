# Takım notu (Arda + Berk) · Build the Builder

Durum ve sahipler burada. Her commit'te güncellenir. Sunucuda: `cd /root/hackathon/build-the-builder && git pull`.

## Durum (Cmt 10 Eki, 15:50)
- Boru hattı canlı: Freya anahtarı çalışıyor, kit base-agent 0/10, kit örnek builder (Opus) ~8-9/10 (slot `brief-a`).
- Bizim derleyici builder: `python3 builder/build.py briefs/brief-a.md tools/openapi.json --cases public-test-set.json --brief A`
  Yol: brief → spec.json (Opus) → compile (sabit topoloji, kod düğümleri) → lint → dry-run → save → smoke → test → patch → export.
  Brief A: v10/v14/**v19 10/10 iki tekrarda** (v19 = güncel: sabit TTS açılış, sessiz tekrar, tek/çok ürün ayrımı); stiller (v10/v11): in_words 10, corrects 9, asks_back 9, pieces 9, talkative 9 (v11). Brief B (A+B spec): v8/**v17 3/3 iki tekrarda**; A-spec ajanı B müşterilerinde de 3/3. Kit örneği: düz 10/10, talkative 7/10. **Dikkat (Cmt 17:00-18:00):** platform modeli yoğunken ajan ilk cümleyi söyleyemiyor, müşteri 80 s sonra kapatıyor → 0/10 görünen koşular platform kaynaklı; `slowest agent turn` uyarısına bak, koşuyu tekrarla. Tam build.py provası: sıfırdan 10/10, 186 s. Agent id'ler `out/compiled/*.ids.json`.
- Kod düğümleri birim testli: `pytest tests/` (takvim, deadline, tarih sözcükleri, geri arama penceresi, outcome seçimi).

## Uç durum seti (Cmt akşam)
- `fixtures/edge-cases.json`: 37 senaryo, 13 müşteri üzerinde (mock özel müşteri kabul etmiyor). Koşturma: `python3 builder/run_custom.py <agent_id> [--only E01,E02] [--reps 2] [--style ...]`.
- Sonuçlar: A v20 20/27 → A v21 25/27 → A+B v21 27/27 → **A v23 37/37 iki tekrarda**; 2. parti A+B v22 10/10; 3. parti (E38-E42) A v24 5/5 + 4/5 (E39 judge varyansı); in_words stiliyle 42 vaka A v24 39/42 → saat sözcüğü, kısmi cevap, not tamlığı düzeltildi → yeniden ölçümde 3/3 × 2. Regresyon kapısı A v24 10/10 × 2, v25 9+10 (PUB-06 taban iki kez → 'bir kez teklif' kuralı, v26).

## Genelleme katmanı (Cmt gece, Opus oturumu)
Gizli brief'lerde alan adları, değerler ve kurallar değişecek; builder artık hiçbirini sabit bilmiyor:
- `builder/apimap.py`: her araç alanı / yanıt bayrağı / outcome değeri `openapi.json`'dan okunur (model bölümü + ad kalıbı yedeği).
- Deadline, ikna teklifleri, taban tutar, hafta sonu kaydırma: spec'teki kural nesnelerinden kodda hesaplanır (`codegen/calendar_lib.py`).
- Çıkarımdan sonra denetim (audit) geçişi: spec brief'e karşı kontrol edilir, kanıtlı düzeltmeler uygulanır (memo geçersiz kılmaları).
- `build.py`: klasör/çok dosya girdisi, kod adımlarının yerel öz-sınaması, brief'e özgü ek özel durumlar için çıkış düğümleri.
- Fixture'lar: `renamed-*` (tüm alanlar/değerler yeniden adlandırılmış), `variant-*` (3 kimlik sorusu, takvim günü deadline, 3 teklif, %20 taban, ek durumlar), `raw-bank-material` (mail+politika+memo).
- `pytest tests/` 15 test (ağsız). Canlı: API eşleme refactor'u A kapı 10/10 × 2, B 3/3 × 2; son aday A v32 / A+B v29 ölçülüyor.

## Sahipler
- Arda: builder kodu (`builder/`), final koşular (Mac, Claude Max login).
- Berk (sunucu): ölçüm koşuları ve hata analizi. LLM gerekmez; `env.sh` yeter.
  1. `source env.sh && python3 tools/run_cases.py <agent_id> --brief A --reps 2 --out results/<ad>.json` (tmux içinde)
  2. Stiller: `--style pieces|corrects|talkative|asks_back|in_words`
  3. Başarısız çağrı: `python3 -c "import freya,json; print(json.dumps(freya.get_call('<call_id>')['messages'],indent=1))"`
     (call_id `results/<ad>.json` içinde). Hangi düğümde, hangi kural, hangi tur → kısa bug listesi.
  4. Sentetik fixture brief'leri: `fixtures/` altına ham-malzeme biçimli bir brief + farklı takvim/kimlik soruları + değişik openapi enum'ları.
- Agent id'ler: `.freya-agents.json` (gitignored) ve `out/<slot>/ids.json`.

## Kredi bütçesi (Cmt 21:20)
- Ölçüm: yaklaşık **0,08 kredi / simüle çağrı** (18,4 kredi ≈ 250 çağrı). Şu an 407 kredi; bugün toplam 1.358 çağrı koştu.
- Final (Paz 20:00): builder gizli brief'lerde simülasyon koşturmaz (pratik müşteri yok), yalnız 1 chat turu → ihmal edilebilir. Puanlamayı organizatör kendi workspace'inde yapar.
- **Rezerv: 100 kredi** (≈1.250 çağrı): gizli brief'lerle pratik müşteri gelirse 2 brief × 30 müşteri × 3 tekrar × 3 tur ≈ 43 kredi + hata düzeltme regresyonları ≈ 25 kredi + pay.
- Harcanabilir: ~300 kredi ≈ 3.800 çağrı. Koruma: `python3 builder/credits.py <çağrı sayısı>` (rezervin altına inecekse 1 döner); `run_custom.py` bunu kendisi yapar. Kit'in `run_cases.py`'sinden önce elle çağır.

## Kurallar
- Tek workspace: aynı anda tek simülasyon; `run_cases.py` bekler. Uzun koşular tmux'ta.
- Anahtarlar `env.sh`'de, asla commit edilmez, asla yazdırılmaz.
- Gizli brief'lerden (Paz 20:00) koda/prompt'a hiçbir kural, değer, isim girmez.
- Workflow limiti: slot ile yerinde güncelleme (`save_workflow(slot)`); yeni slot açma.
