# BTC 5-Minute Up/Down Predictor

Paper-trading simülatörü — gerçek para veya API bağlantısı kullanmaz.

## Proje Yapısı

```
app/
├── main.py              # CLI giriş noktası
├── config.py            # Tüm konfigürasyon (.env'den yüklenir)
├── logger.py            # Merkezi loglama kurulumu
├── scheduler.py         # Pencere zamanlayıcısı
├── models/
│   ├── candle.py        # OHLCV veri modeli
│   ├── signal.py        # Decision, MarketRegime, FeatureSet, SignalResult
│   └── trade.py         # TradeRecord
├── data/
│   ├── base_provider.py # Soyut veri sağlayıcı arayüzü
│   ├── binance_provider.py  # Binance public REST API (auth gerekmez)
│   └── buffer.py        # Rolling candle buffer
├── features/
│   ├── indicators.py    # EMA, RSI, ATR, momentum, z-score, ...
│   └── extractor.py     # Tüm feature'ları üretir
├── regime/
│   └── detector.py      # Piyasa rejimi sınıflandırması
├── strategy/
│   ├── signals.py       # Bireysel sinyal fonksiyonları [-1, +1]
│   └── ensemble.py      # Ağırlıklı toplam → karar motoru
├── risk/
│   └── manager.py       # Stake, günlük limit, cooldown
├── simulation/
│   ├── paper_trade.py   # OpenTrade / resolve_trade
│   └── engine.py        # LiveSimulationEngine + BacktestEngine
├── reporting/
│   ├── metrics.py       # Performans metrikleri
│   └── reporter.py      # CSV/JSON kayıt + konsol özet
└── notifier/
    ├── base_notifier.py  # Soyut bildirim arayüzü
    └── mock_notifier.py  # Log-based mock (Telegram için genişletilebilir)
tests/
├── test_features.py
├── test_regime.py
├── test_strategy.py
├── test_risk.py
└── test_simulation.py
```

## Kurulum

```bash
# 1. Sanal ortam oluştur
python -m venv .venv

# Windows
.venv\Scripts\activate

# 2. Bağımlılıkları yükle
pip install -r requirements.txt

# 3. .env dosyasını oluştur
copy .env.example .env
# (veya: cp .env.example .env)

# .env içini ihtiyaca göre düzenle
```

## Kullanım

### Canlı Simülasyon (Gerçek Zamanlı)
```bash
python -m app.main live
```
Her 5 dakikada bir Binance'ten veri çeker, karar üretir, sonucu değerlendirir.
Gerçek işlem yapılmaz — tamamen sanal bakiye ile çalışır.

### Backtest (Geçmiş Veri)
```bash
python -m app.main backtest --file data/btc_1m.csv
```
CSV formatı (başlık satırı gerekli):
```
timestamp,open,high,low,close,volume
2024-01-01T00:00:00Z,42000,42100,41900,42050,1500
...
```
Timestamp: ISO 8601 string veya Unix timestamp (saniye/milisaniye).

### Rapor Görüntüle
```bash
python -m app.main report
```
`reports/` klasöründeki en son JSON raporunu yükler ve özeti basar.

### Testleri Çalıştır
```bash
# Temel
pytest tests/

# Coverage ile
pytest tests/ --cov=app --cov-report=term-missing
```

## Örnek Konsol Çıktısı

```
2024-01-15 08:00:00 | INFO     | simulation.engine | ▶ New window: 08:00 → 08:05
2024-01-15 08:00:01 | INFO     | strategy.ensemble | Decision=UP       | confidence= 61.3 | regime=TREND_UP | aggregate=+0.245
2024-01-15 08:00:01 | INFO     | simulation.engine |   Decision: UP         | Conf:  61.3 | Stake: 10.00 | Price: 43250.00
2024-01-15 08:05:00 | INFO     | simulation.engine |   ✓ Resolved: open=43250.00 close=43318.00 | PnL=+10.00 | Balance=1010.00
```

## Konfigürasyon (.env)

| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `INITIAL_BALANCE` | 1000.0 | Başlangıç sanal bakiyesi |
| `STAKE_MODE` | fixed | `fixed` veya `percent` |
| `STAKE_FIXED` | 10.0 | Her bahiste sabit tutar |
| `CONFIDENCE_THRESHOLD` | 55.0 | Bu altında → NO_TRADE |
| `MAX_DAILY_LOSS` | 50.0 | Günlük maksimum zarar |
| `MAX_CONSECUTIVE_LOSSES` | 3 | Cooldown tetikleme eşiği |
| `COOLDOWN_WINDOWS` | 2 | Cooldown süresi (pencere sayısı) |
| `ATR_RATIO_MAX` | 2.5 | Aşılırsa → NO_TRADE (aşırı volatilite) |
| `NOISE_SCORE_MAX` | 0.7 | Aşılırsa → NO_TRADE (gürültülü piyasa) |
| `LOG_LEVEL` | INFO | DEBUG / INFO / WARNING |

## Sistem Nasıl Çalışır?

```
Her 5 dakikada bir:

[Binance REST] ──► [CandleBuffer]
                         │
                    [FeatureExtractor]
                    ├── EMA(5/9/20)
                    ├── RSI(14)
                    ├── ATR(14)
                    ├── Returns (1/3/5/10/15m)
                    ├── Z-Score
                    ├── Momentum
                    ├── Volatility
                    ├── Volume Spike/Trend
                    └── Composite Scores
                         │
                    [RegimeDetector]
                    (TREND_UP / DOWN / SIDEWAYS
                     HIGH_VOL / LOW_VOL / CHAOTIC)
                         │
                    [EnsembleDecisionEngine]
                    ├── 8 sinyal fonksiyonu → [-1, +1]
                    ├── Rejime göre ağırlıklandırma
                    ├── Volatility hard filter
                    └── Confidence [0-100]
                         │
                    [RiskManager]
                    ├── Stake hesapla
                    ├── Daily limit kontrolü
                    └── Cooldown kontrolü
                         │
                    UP / DOWN / NO_TRADE
                         │
                    5 dk bekle → close fiyatı al → PnL hesapla
                         │
                    [Reporter] → CSV + JSON
```

## Telegram Bildirimleri (Opsiyonel)

`app/notifier/mock_notifier.py` dosyasını genişleterek Telegram ekleyebilirsiniz:

```python
class TelegramNotifier(MockNotifier):
    def __init__(self, token: str, chat_id: str):
        self._bot = telegram.Bot(token=token)
        self._chat_id = chat_id

    def on_decision(self, result, stake, open_price):
        super().on_decision(result, stake, open_price)
        self._bot.send_message(
            self._chat_id,
            f"🔔 {result.decision.value} | conf={result.confidence:.1f} | stake={stake}"
        )
```

## Lisans

Eğitim ve araştırma amaçlıdır. Gerçek para ile kullanmak için kendi sorumluluğunuzdur.
