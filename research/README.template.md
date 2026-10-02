# Prediction-Market Research Agent

[![tests](https://github.com/takakhoo/prediction-market-research-agent/actions/workflows/offline.yml/badge.svg)](https://github.com/takakhoo/prediction-market-research-agent/actions/workflows/offline.yml)

**Most of the edge you can measure in a prediction market disappears when you try to trade it. This repo measures how much is left, on {{nMarkets}} resolved Polymarket markets and ${{volumeB}} billion of volume.**

Polymarket prices are read as probabilities, and every gap between price and outcome looks like a trading rule. We rebuilt {{tapeFills}} real fills, priced tens of thousands of contracts as options on the asset underneath them, trained models, asked language models, and then put every apparent edge through the same sequence of controls: real fills, fair estimators, old information, limited capital, fees, and a confirmation period picked in advance.

![One real contract: Polymarket fills against the option model](results/figures/demo.gif)

*One real crypto threshold contract, chosen by a fixed rule (among contracts whose spot price crossed the strike in the last 36 hours, the one where the option-model rule staked the most). Blue dots are actual Polymarket fills. The orange line is what a textbook digital-option formula says the contract is worth, using only the spot price and trailing volatility available one minute earlier.*

## The result

![The same rule under each successive control](results/figures/ladder.png)

One rule, "take the side the option model prefers when it disagrees with the price by ten cents", scored five ways on crypto threshold contracts:

| How it is scored | Return on stake |
|---|---|
| At displayed prices, the way a quick backtest would | {{displayedRule}} |
| At fills that happened, model sees 1-minute-old spot, after fees | **{{backedOne}}** |
| Same, model sees 15-minute-old spot | {{backedFifteen}} |
| Capped at $200 per fill, 15-minute-old spot, whole sample | {{replayAll}} (Sharpe {{replaySharpe}}, t = {{replayT}} on daily returns, deflated Sharpe probability {{replayDSR}}) |
| Confirmation period, April to September 2026 | {{replayConfirm}} (t = {{replayConfirmT}}) |

What we found, in order of how sure we are:

- **Displayed prices lie where nobody trades.** {{dormantShare}} of price-history snapshots have had no trade in a day. Their midpoints sit near 0.5 and resolve Yes {{dormantGap}} points less often than shown. That is the famous "Yes bias", and most of it cannot be traded.
- **The favorite-longshot bias has whatever sign your estimator gives it.** On the same fills, pooling says Yes prices of 0.8 to 0.9 are too low by {{pooledHighMag}} points. One bet per market at the first fill in that band says they are too high by {{ftHighMag}} points.
- **A textbook option formula knows as much as the price.** On crypto threshold contracts the best forecast puts weight {{encPrice}} on the fill price and {{encModel}} on the formula. Takers who trade against the formula by ten cents lose {{opposedOneLoss}}.
- **That edge is a speed race, and it is closing.** It shrinks as the formula's data ages ({{backedFifteen}} with 15-minute-old spot), and it shrank when fees arrived: endorsed fills returned {{lastQuarterEndorsed}} in {{lastQuarter}}.
- **First prints overshoot, in tiny size.** The first fill of a market inside a high price band is about eleven points too high. Buying No at the next real fill returned {{fadeMid}} after fees, on fills with a median stake of ${{fadeFillUsd}}.
- **A learned model beats the price, modestly.** Trained walk-forward on {{modelTestMarkets}} test markets, a boosted residual model with order-flow, wallet, and option-value features improves the Brier score of the last traded price by {{skillResFullAll}} ({{skillResFullHold}} on the last five months). On price-linked contracts the bare formula beats the displayed quote by {{plMidFair}}.
- **The standard fixes do not.** Platt and isotonic recalibration lose to the raw price out of time. Sorting wallets by past return does not sort their future return. Claude Fable 5.1, Sonnet, and Haiku with no retrieval score {{llmBlindFable}}, {{llmBlindSonnet}}, and {{llmBlindHaiku}} against the market's {{llmMarket}} on {{llmN}} questions opened after their training cutoffs.

Paper: [`paper/main.pdf`](paper/main.pdf). Target venue: **ACM EC 2027** (ACM Conference on Economics and Computation), with KDD 2027 as the backup. The EC 2027 call is not out yet, so the deadline is an estimate from last year (early February 2027). Venue notes are in [`paper/VENUES.md`](paper/VENUES.md).

Nothing here is investment advice. The repo places no orders.

## Contents

- [The data](#the-data)
- [The science, step by step](#the-science-step-by-step)
- [What it means for stocks and investing](#what-it-means-for-stocks-and-investing)
- [Try it](#try-it)
- [The monitoring application](#the-monitoring-application)
- [What happened to v1](#what-happened-to-v1)
- [Reproduce](#reproduce)

## The data

![Resolved markets per quarter](results/figures/dataset.png)

Everything comes from public endpoints with no credentials.

| Layer | What | Size |
|---|---|---|
| Markets | every closed Polymarket market with at least $1,000 volume, with rules, tags, fee schedule | {{nMarkets}} markets, ${{volumeB}}B |
| Fills | complete taker-trade histories with wallets, on a stratified random sample | {{tapeFills}} fills, {{tapeMarkets}} markets, ${{tapeUsdB}}B staked |
| Quotes | midpoint price paths | {{quoteMarketsK}} thousand markets |
| Underlyings | Binance 1-minute candles (BTC, ETH, SOL, XRP), Deribit DVOL, hourly and daily equity bars | 2024 to October 2026 |
| Forecasts | 1,692 language-model forecasts on {{llmN}} post-cutoff questions | three models, two conditions |

Replaying each price-linked contract's settlement rule on the underlying data reproduces Polymarket's official outcome for 99.97% of Binance-settled crypto threshold contracts and 99.9% of single-stock contracts. Settlement times are read from each contract's rules. The API's end time is wrong for about 3% of threshold contracts, by up to 16 hours.

## The science, step by step

### 1. A third of displayed prices are parked

![Dormant quotes fake a Yes bias](results/figures/midpoint_artifact.png)

Polymarket's price history is a quote midpoint. A book with a bid at one cent and an ask at 99 cents has a midpoint of 0.50. {{dormantZone}} of dormant snapshots sit between 0.4 and 0.6, against {{activeZone}} of active ones, and in ordinary Yes/No markets they resolve Yes {{dormantGap}} points less often than displayed. Active snapshots are off by {{activeGap}} points. Any calibration curve or backtest built on the price-history endpoint inherits this.

Everything after this section uses prices that traded.

### 2. Same fills, opposite answers

![Two estimators on the same fills](results/figures/estimators.png)

If fill prices are fair, outcome minus price averages zero under any rule that only looks backward. Two such rules disagree in sign:

- **Pool every fill**, weighted by shares. Markets count in proportion to how much they trade inside a band, and volume piles up where a contract is on its way to resolving.
- **First touch**, one bet per market at the first fill inside the band. {{spikeShare}} of those moments are a single order sweeping a thin book and paying {{spikeGapMag}} points too much.

A third common choice, averaging each market's return ratio, is biased upward even when prices are fair, so we do not use it. Buying the favorite at its first fill between 0.70 and 0.85 returned {{firstEntryMid}} across {{firstEntryMidN}} markets.

### 3. Who wins

![Taker returns by category](results/figures/maker_taker.png)

Across ${{tapeUsdB}} billion of taker stake, takers earned {{takerNet}} after fees. There is no aggregate maker-taker transfer of the kind reported on Kalshi. The exception is the 5-minute and 15-minute crypto up/down contracts, where takers lose {{updownTakerLoss}} and fees take {{updownFee}} of stake.

At scheduled snapshots, last-trade prices are slightly too extreme early in a market's life (calibration slope {{slopeEarly}}) and close to right at the end ({{slopeLate}}).

### 4. An event contract is a digital option

"Will Bitcoin be above $82,000 at noon on February 9?" pays one dollar or nothing. That is a cash-or-nothing call, and with spot $S$, strike $K$, time left $\tau$, and volatility $\sigma$ it is worth

$$\hat p = \Phi\left(\frac{\ln(S/K) - \tfrac{1}{2}\sigma^2\tau}{\sigma\sqrt{\tau}}\right)$$

We use trailing realized volatility and the last one-minute candle that closed before each fill. Nothing is fitted.

![Fill price against the option model](results/figures/options_brier.png)

On {{thrMarkets}} threshold contracts the formula and the fill price are tied at every horizon, and each carries information the other lacks. On the short up/down contracts the market wins outright (weight on the formula: {{encUpdown}}).

![Implied against realized volatility](results/figures/implied_vol.png)

Backing volatility out of Polymarket fills gives a number within {{ivRatioLow}} to {{ivRatioHigh}} of what was realized afterwards. Listed options usually charge a premium over realized volatility. These contracts do not.

The same construction on {{stockMarkets}} contracts on NVDA, TSLA, AAPL, and other single-stock closes gives the formula weight {{stockEncModel}}. Takers who trade against it by ten cents lose {{stockOpposedLoss}}.

### 5. The edge, and how it fades

![The edge by data age and by quarter](results/figures/edge_decay.png)

Fills the formula endorses returned {{backedOne}} to the taker after fees; fills it opposes returned {{opposedOne}}. Give the formula older spot data and the edge shrinks: {{backedFive}} at 5 minutes, {{backedFifteen}} at 15, {{backedSixty}} at 60. Most of it is a speed race. At 5 and 15 minutes the estimate is still positive but its interval reaches zero, and at an hour nothing is left.

![Replay of the rule on real fills](results/figures/equity.png)

A capital-constrained replay (15-minute-old data, $200 per fill, profit booked at expiry) made ${{replayPnlK}} thousand on at most ${{replayCapitalK}} thousand deployed. On daily returns that is a Sharpe ratio of {{replaySharpe}} with t = {{replayT}}: the pooled fill-level interval excludes zero, the day-by-day series does not. The ten-cent threshold was set on contracts expiring before April 2026. After that the rule returned {{replayConfirm}}, as a 7% crypto fee rate reached every contract and the stake clearing the bar fell by a factor of five or more.

The single-stock version is smaller and cleaner: {{stockReplayAll}} on stake with at most ${{stockReplayCapitalK}} thousand deployed, Sharpe {{stockReplaySharpe}}, deflated Sharpe probability {{stockReplayDSR}}, and {{stockReplayConfirm}} in the confirmation period.

### 6. Can anything else beat the price?

![Out-of-time challengers](results/figures/models.png)

Every challenger is trained walk-forward: a model tested in a given month has seen only markets that had already resolved. {{modelTestMarkets}} test markets, last-trade Brier {{modelMarketBrier}}.

| Challenger | Brier skill vs price, all months | Last five months (May to Sep 2026) |
|---|---|---|
| Quote midpoint | {{skillMidAll}} | {{skillMidHold}} |
| Platt recalibration | {{skillPlattAll}} | {{skillPlattHold}} |
| Isotonic recalibration | {{skillIsotonicAll}} | {{skillIsotonicHold}} |
| Boosted residual model: path, flow, wallet records | {{skillResFlowAll}} | {{skillResFlowHold}} |
| Boosted residual model plus option value | {{skillResFullAll}} | {{skillResFullHold}} |
| Price and option value, two-parameter blend | {{skillBlendAll}} | {{skillBlendHold}} |

Positive is better than the price. The residual models start from the price and learn a correction, so with no signal they return the price itself. Both feature families help, and the option value helps most: on the {{plMarkets}} price-linked test markets the two-parameter blend improves on the last trade by {{plSkillBlend}} and on the quote midpoint by {{plMidBlend}}. No setting was chosen on the last five months, but we did see scores for these configurations on those months on an earlier, smaller tape, so treat that column as a late-period check and not a pristine holdout.

![Language models against the market](results/figures/llm.png)

Language models get the question, the rules, and the date. Blind, all three are close to always guessing the base rate ({{llmBase}}). Shown the market price, they return it almost unchanged.

Wallet records: fills by wallets with no resolved history returned {{firstTimers}}; seasoned wallets returned {{seasoned}}. Sorting seasoned wallets by past return does not sort their future return in this sample, which covers only part of each wallet's history.

### 7. First prints overshoot

The first fill of a market inside a Yes-price band of 0.8 to 0.9 is {{ftHighMag}} points above the outcome frequency. To trade that, you need a later price. Buying No at the next fill where a taker bought No, at least a minute later and only if the price is still within five cents of the band (median wait {{fadeWait}} minutes), returned {{fadeMid}} for the 0.6 to 0.8 band and {{fadeHigh}} for 0.8 to 0.98, after fees. From April 2026 on: {{fadeMidLate}} and {{fadeHighLate}}. Dropping the trigger and simply taking each market's first No-buying fill in the same price range returned {{fadeMidBase}} and {{fadeHighBase}}, so the result does not depend on reacting to the first print.

The catch is size. The fills this rule copies have a median stake of ${{fadeFillUsd}}, and ${{fadeTotalK}} thousand in total across both bands. It describes thin books early in a market's life and has almost no capacity.

## What it means for stocks and investing

This project started as a prediction-market tool. The parts that transfer:

1. **A quote is evidence only if someone could trade it.** The largest "bias" in this dataset came from prices nobody could hit. The same applies to stale closes in thin stocks, wide option quotes, and any backtest on mid prices.
2. **Price the derivative from the underlying first.** A threshold contract on NVDA or Bitcoin has a model price from spot and volatility. When the market and that price disagreed by a wide margin, the market was wrong more often. That is the same check an options trader runs against implied volatility.
3. **Ask how an estimate could be executed.** Pooled averages and one-bet-per-market rules gave opposite signs here. A number that does not come with an executable rule is a description, and it may flip.
4. **Edges decay, and fees move first.** The option-model rule was worth about 17% per dollar staked until a fee of at most 1.75 cents a share arrived.
5. **Size matters.** The rule never deployed more than ${{replayCapitalK}} thousand. Returns on that scale do not carry to a large account.

## Try it

Run the research tests (pricing identities, fee math, look-ahead guards). No data needed:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-research.txt
python -m pytest tests/research -q
```

Regenerate the figures and this README from the committed result tables (the dataset chart needs the raw market pull and is skipped without it):

```bash
python -m research.figures
```

```bash
python -m research.facts
```

Score the committed language-model forecasts against the market:

```bash
python -m research.experiments.e8_llm
```

## The monitoring application

The original application in `src/` finds markets where local news may be evidence, discovers Telegram channels, and classifies messages for human review. It stops at review and does not trade. Its setup guide moved to [`docs/LIVE_SETUP.md`](docs/LIVE_SETUP.md). The credential-free check still works:

```bash
pip install -r requirements-offline.txt
python -m pytest -q --ignore=tests/research
python scripts/offline_replay.py
```

## What happened to v1

The first paper built on this application ([agent-evidence-evaluation](https://github.com/takakhoo/agent-evidence-evaluation)) reported a 5.8-hour news lead time and a 58% reduction in review load. The lead times came from randomly generated timestamps and the review-load number from a confounded comparison. Both were withdrawn. This version starts from the other end: measured outcomes on real markets, with each claim tested against the price a trader could have had.

The same habit caught four problems inside this project before they reached a table: the parked midpoints of section 1, the biased per-market ratio of section 2, an option-model "win" over the market that existed only at displayed prices, and a batch of contracts whose listed end time was 16 hours before the candle their rules settle on, which made the option model look sharper than it was.

## Reproduce

The raw pulls are about 4 GB and take a few hours at the public rate limits:

```bash
python -m research.collect.markets
python -m research.collect.build_universe
python -m research.collect.prices
python -m research.collect.crypto
python -m research.collect.stocks
python -m research.collect.trades --ids research/data/derived/trade_ids.parquet
```

Then every table and figure:

```bash
./research/run_all.sh
```

| Step | Script | Table |
|---|---|---|
| Fill tape and snapshot panel | `research/experiments/build_tape.py` | `research/data/derived/` |
| Dormant midpoints, calibration | `e1_e2_calibration.py` | `results/tables/e1_e2_calibration.json` |
| Makers, takers, fees | `e3_maker_taker.py` | `e3_maker_taker.json` |
| Pooled, first touch, fade | `e3b_first_touch.py` | `e3b_first_touch.json` |
| Crypto contracts as options | `e4_crypto_options.py` | `e4_crypto_options.json` |
| Walk-forward model comparison | `e5_model.py` | `e5_model.json` |
| Capital-constrained replay | `e6_backtest.py` | `e6_backtest.json` |
| Wallet records | `e7_wallets.py` | `e7_wallets.json` |
| Language models | `e8_llm.py` | `e8_llm.json` |
| Single-stock contracts as options | `e9_stock_options.py` | `e9_stock_options.json` |

Limits worth knowing: fills are a sample, so wallet histories are partial. The trade feed shows the taker side only. Stock inputs are hourly bars with no extended-hours data. Fills bound the size each rule could have traded. The confirmation period is six months. Language-model forecasts came from subagents instructed to use no tools; every run made exactly the file read and write the protocol required.

This repository has no license grant and is provided for research review.
