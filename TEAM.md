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
- Sonuçlar: A v20 20/27 → A v21 25/27 → A+B v21 27/27 → **A v23 37/37 iki tekrarda**; 2. parti A+B v22 10/10; 3. parti (E38-E42) A+B v22 4/5 → deneme sayma kuralı netleştirildi, A v24 / A+B v23 ölçülüyor. Regresyon kapısı A v23: 10/10 × 2.

## Sahipler
- Arda: builder kodu (`builder/`), final koşular (Mac, Claude Max login).
- Berk (sunucu): ölçüm koşuları ve hata analizi. LLM gerekmez; `env.sh` yeter.
  1. `source env.sh && python3 tools/run_cases.py <agent_id> --brief A --reps 2 --out results/<ad>.json` (tmux içinde)
  2. Stiller: `--style pieces|corrects|talkative|asks_back|in_words`
  3. Başarısız çağrı: `python3 -c "import freya,json; print(json.dumps(freya.get_call('<call_id>')['messages'],indent=1))"`
     (call_id `results/<ad>.json` içinde). Hangi düğümde, hangi kural, hangi tur → kısa bug listesi.
  4. Sentetik fixture brief'leri: `fixtures/` altına ham-malzeme biçimli bir brief + farklı takvim/kimlik soruları + değişik openapi enum'ları.
- Agent id'ler: `.freya-agents.json` (gitignored) ve `out/<slot>/ids.json`.

## Kurallar
- Tek workspace: aynı anda tek simülasyon; `run_cases.py` bekler. Uzun koşular tmux'ta.
- Anahtarlar `env.sh`'de, asla commit edilmez, asla yazdırılmaz.
- Gizli brief'lerden (Paz 20:00) koda/prompt'a hiçbir kural, değer, isim girmez.
- Workflow limiti: slot ile yerinde güncelleme (`save_workflow(slot)`); yeni slot açma.
