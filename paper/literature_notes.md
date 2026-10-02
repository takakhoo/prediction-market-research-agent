# Literature notes: prediction-market efficiency and links to mainstream finance

Compiled 2026-10-02. Companion to `refs.bib` (70 entries). Citation keys below match the bib file.

## How to read these notes

Each entry states how deep the reading went:

- **abstract only**: the abstract or landing page was read, nothing else.
- **full text (HTML)**: the arXiv HTML version was read through a fetch tool that returns a summary of the page. Numbers came from that summary.
- **PDF pages read**: the PDF was opened and the listed pages were read directly.
- **metadata only**: title, authors, and year were confirmed in the DOI registry (Crossref). No abstract was available, so no findings are described.
- **secondary coverage**: numbers come from a news article or institutional summary about the paper, because the paper page itself returned HTTP 403 (SSRN, Wiley, Taylor and Francis, CEPR, and Columbia all blocked the fetch tool).

Two caveats apply to everything here. First, most pages were read through a summarizing fetch tool, so every number should be rechecked against the PDF before it goes into the paper. Second, several 2025-2026 items are unrefereed preprints or blog posts. The bib `verifiedvia` field records the confirmation route for each entry.

## Corrections to the titles and details in the brief

- Clinton and Huang: versions 1 to 3 (December 2025) were titled "Prediction Markets? The Accuracy and Efficiency of $2.4 Billion in the 2024 Presidential Election". Version 5 (10 June 2026) is retitled "...of Political Prediction Markets in the 2024 Presidential Election" and its abstract reports different headline numbers from the early press coverage. See the entry below.
- Reichenbach and Walther: the SSRN title is "Exploring Decentralized Prediction Markets: Accuracy, Skill, and Bias on Polymarket" (2025).
- Becker: first published as a blog post on jbecker.dev in January 2026. An SSRN version with the same title has a 2026 DOI record.
- Bürgi, Deng and Whelan: circulates as CESifo WP 12122 (2026), and also as UCD, CEPR, MPRA, and GWU working papers. The January 2026 draft was read.
- Diercks, Katz and Wright: NBER WP 34702 (January 2026) and Federal Reserve FEDS 2026-010 (February 2026).
- Prophet Arena: the paper is titled "LLM-as-a-Prophet: Understanding Predictive Intelligence with Prophet Arena".
- KalshiBench: single author (Lukas Nel), arXiv 2512.16030.
- Columbia wash-trading study: "Network-Based Detection of Wash Trading" by Sirolly, Ma, Kanoria and Sethi (SSRN, November 2025).

---

## A. Prediction market accuracy, calibration, favorite-longshot bias

### A1. Classic anchors

**wolfers2004prediction** (Wolfers and Zitzewitz, JEP 2004). Abstract only. Survey of early prediction markets. Market forecasts are "typically fairly accurate" and beat most moderately sophisticated benchmarks. Contract design can reveal probabilities, means, medians, and uncertainty, and conditional markets reveal beliefs about regression coefficients, with the usual correlation versus causation problem.
*Implication:* this is the baseline claim our calibration experiments test on 2024-2026 data.

**wolfers2006interpreting** (Wolfers and Zitzewitz, NBER WP 12200). Abstract only. Response to Manski. Across a range of models, prices of binary contracts are close to the mean belief of traders. Risk aversion and the shape of the belief distribution drive the gap between price and mean belief.
*Implication:* justifies treating price as a probability estimate to first order, and tells us the residual wedge should grow with belief dispersion.

**manski2006interpreting** (Manski, Economics Letters 2006). Abstract only (NBER version). With risk-neutral, budget-constrained traders holding heterogeneous beliefs, price only partially identifies the mean belief: the mean lies in an interval with the price at its midpoint. Bürgi et al. restate the bound as mean belief between p^2 and 2p - p^2 for price p.
*Implication:* at p = 0.5 the bound is [0.25, 0.75], so mid-range prices carry the least information about mean belief. Our reliability diagrams should report uncertainty by price bucket.

**snowberg2010explaining** (Snowberg and Wolfers, JPE 2010). Abstract only. Uses a large horse-racing dataset and compound bets (exacta, quinella, trifecta) to separate risk-love from probability misperception as explanations of the favorite-longshot bias. The evidence favors misperception, as in prospect theory.
*Implication:* if FLB on Polymarket and Kalshi comes from misperception, it should appear in every category with retail flow and shrink where professional makers dominate. Compare with Becker and Bürgi below.

**page2013prediction** (Page and Clemen, Economic Journal 2013). Abstract only. Model and data (Intrade transaction prices) show calibration depends on time to expiration. Prices are reasonably calibrated near expiry and biased toward a favorite-longshot pattern for events far in the future. The bias is exploitable only at low discount rates.
*Implication:* condition every calibration result on time to resolution, and adjust long-horizon returns for the time value of locked capital.

**ottaviani2010noise** (Ottaviani and Sørensen, AEJ Micro 2010). Abstract only. Theory for parimutuel markets. The sign and size of the favorite-longshot bias depend on the ratio of private information to noise, which in turn depends on the number of bettors, number of outcomes, and recreational participation.
*Implication:* predicts cross-sectional variation in FLB by market thickness and number of outcomes, which we can test across multi-outcome events.

**ottaviani2015price** (Ottaviani and Sørensen, AER 2015). Abstract only. In a binary market with heterogeneous priors and bounded stakes (or decreasing absolute risk aversion), the equilibrium price underreacts to information. Underreaction grows with belief heterogeneity and produces short-run momentum and long-run reversal.
*Implication:* this is the theory behind a post-news drift test in prediction markets. It predicts drift should be larger in contested markets.

**berg2008prediction** (Berg, Nelson and Rietz, IJF 2008). Abstract only (IDEAS). Iowa Electronic Markets against 964 polls over five US presidential elections (1988 to 2004). The market is closer to the outcome 74% of the time and beats polls in every election at horizons over 100 days.
*Implication:* a long-horizon accuracy benchmark for the market-versus-polls comparison.

**erikson2008political** (Erikson and Wlezien, POQ 2008). Abstract only. Challenges Berg et al. When poll leads are discounted properly into forecasts, poll-based forecasts beat IEM vote-share prices, and poll-based win projections beat winner-take-all prices. Traders price in more campaign uncertainty than polls warrant.
*Implication:* the comparison baseline matters. Compare markets to a model built on polls rather than to raw polls.

**atanasov2017distilling** (Atanasov et al., Management Science 2017). Abstract only. Randomized comparison with more than 2,400 forecasters and 261 geopolitical events over two seasons. Market prices beat the simple mean of poll forecasts. Team polls with temporal decay, performance weighting, and recalibration beat the market, with the largest gap early in long-duration questions.
*Implication:* statistical aggregation and recalibration can beat raw market prices. This supports testing a recalibrated-price baseline.

**hanson2009manipulator** (Hanson and Oprea, Economica 2009). Abstract only. Kyle-style model. A manipulator with an uncertain target price can raise average price accuracy by raising the returns to informed trading.
*Implication:* theory prior against large persistent manipulation effects. Contrast with the field evidence in Rasooly and Rozzi.

### A2. Recent evidence on Kalshi and Polymarket

**burgi2026makers** (Bürgi, Deng and Whelan, CESifo WP 12122). PDF pages 1 to 5 read (January 2026 draft). Data: 46,282 Kalshi contracts from 12,403 events, market open in 2021 through April 2025, each open at least 24 hours, giving over 300,000 prices. Prices become more accurate toward close, with a clear favorite-longshot bias: contracts under 10 cents lose over 60% of the money invested, contracts above 50 cents earn a small positive return, and the average return across contracts is about minus 20%. Makers earn more than takers, and both show the bias. The authors report some evidence the bias is shrinking over time.
*Implication:* replicate the return-by-price-bucket curve, split by maker and taker, on data after April 2025, and test whether the bias has kept shrinking.

**becker2026microstructure** (Becker, jbecker.dev and SSRN 2026). Blog page and SSRN abstract read. Data: 72.1 million Kalshi transactions, June 2021 through November 2025 (the blog reports $18.26 billion in volume). Takers earn a mean excess return of -1.12% per trade and makers +1.12%. YES contracts underperform NO contracts of the same cost basis by up to 64 percentage points at longshot prices, which the author calls an optimism tax. The blog reports 5-cent contracts winning 4.18% of the time and 95-cent contracts 95.83%. The maker-taker gap ranges from 0.17 points in finance to more than 7 in world events and media, and the SSRN abstract says the gap reversed by 5.3 points after post-election volume growth brought in professional liquidity providers. A decomposition attributes about three quarters of taker losses to execution within price-direction cells and almost none to selection across price levels.
*Implication:* test the YES/NO asymmetry at matched cost basis, and separate "who was the taker" from "what was the price" in every return calculation. Not peer reviewed.

**reichenbach2025exploring** (Reichenbach and Walther, SSRN 2025). Metadata only. Title, authors, and year confirmed. The SSRN page was blocked, so no findings are described here. A search snippet from press coverage mentioned 124 million trades and $48 billion in volume. That number was not read in the paper.
*Implication:* read the PDF before citing any result.

**clinton2026prediction** (Clinton and Huang, SocArXiv v5, June 2026). Abstract only (v5). Nearly 2,200 political markets and more than $3.2 billion in platform-reported volume across IEM, Kalshi, PredictIt, and Polymarket in the final nine weeks of the 2024 campaign. 86% of actively traded markets did better than a coin flip and markets were generally well calibrated, with modest longshot bias. 66% of markets were priced below $0.20 or above $0.80 on election eve and 96% of those resolved as priced. Among markets priced $0.40 to $0.60 (12% of the sample), 55% resolved for the favorite. Daily price changes across related markets were far less synchronized than price levels, and arbitrage opportunities in winner-take-all presidential markets existed on nearly every day. Press coverage of the December 2025 version reported platform accuracy of 67% (Polymarket), 78% (Kalshi), and 93% (PredictIt). Those figures are from news articles and do not appear in the v5 abstract.
*Implication:* headline accuracy is driven by contract composition. Report accuracy within price buckets, and cite v5 rather than the press numbers.

**saguillo2025unravelling** (Saguillo, Ghafouri, Kiffer and Suarez-Tangil, arXiv 2508.03474). Full text (HTML). Polymarket on-chain data, 1 April 2024 to 1 April 2025, 17,218 conditions. 7,051 conditions showed at least one rebalancing arbitrage (outcome prices not summing to $1). Combinatorial arbitrage across markets was rare: 13 dependent pairs during the election period, about $95K. Realized arbitrage profit is estimated at about $40 million in total. The top arbitrageur made $2.01 million over 4,049 transactions. An LLM (DeepSeek-R1 distill) was used to detect dependent markets, with 81.45% accuracy on single-market checks.
*Implication:* within-market sum-to-one violations are the large, crowded opportunity. Cross-market semantic arbitrage was small in that window. Any backtest of these must model execution against the order book.

**cardozo2026favorite** (Cardozo and Rivero-Wildemauwe, arXiv 2609.12878). Abstract only. 588 million Polymarket trades across 2.48 million accounts. In raw trades, purchases below 10 cents lose 19.3 cents per dollar and purchases at or above 90 cents earn 0.83 cents. The sign depends on weighting: grouping contracts by parent event, longshots gain 4.1 cents per dollar, and weighting individuals equally gives a loss of 6.3 cents. The bias appears in crypto and politics and is absent in sports.
*Implication:* FLB estimates are sensitive to the unit of observation. Report trade-weighted, contract-weighted, and event-clustered versions side by side.

**le2026decomposing** (Le, arXiv 2602.19520). Full text (HTML). 353 million trades across about 429,000 binary contracts on Kalshi and Polymarket. Calibration is summarized by logistic recalibration slopes (slope above 1 means prices are compressed toward 50%). Kalshi politics slopes run 1.19 to 1.83 across horizons, and large political trades (over 100 contracts) show slope 1.74 against 1.19 for single contracts. Polymarket politics mean slope is 1.45. Sports are well calibrated at short horizons (0.90 to 1.10) and compressed at one month or more (1.74). Short-horizon weather is overconfident (0.69 to 0.97). Reported Brier scores: politics 0.119, sports 0.185, crypto 0.174. A decomposition explains 87.3% of slope variance in sample (71.5% out of sample), and a Bayesian measurement-error model attributes roughly half the raw slope variation to estimation noise.
*Implication:* a domain-by-horizon recalibration map is the natural first trading signal to test, and about half of its apparent structure may be noise. Use event-clustered inference.

**walker2026price** (Walker, Princeton senior thesis 2026). Abstract only. 188,509 resolved binary Polymarket markets and 1,875,570 daily price observations, November 2022 to December 2025. Brier Skill Score 0.398 overall, from 0.264 in sports to 0.565 in politics. Overall logistic recalibration slope b = 1.112, consistent with favorite-longshot bias, present in every domain and worse at long horizons. Event-level clustered bootstrap widens intervals enough that two horizon bands lose significance.
*Implication:* a replication target with a published slope. Clustered bootstrap by event should be our default. Undergraduate thesis, so treat as a lead to verify.

**gomezcram2026prediction** (Gomez-Cram, Guo, Jensen and Kung, SSRN 2026). SSRN abstract plus Yale Insights summary (secondary coverage for the numbers). Universe of Polymarket transactions: 1.72 million accounts, 98,906 events, 210,322 markets, $13.76 billion volume. About 3% of accounts are persistently skilled and generate most price discovery. Their trades predict future prices and outcomes and react to news as it arrives. Skill persists: 44% of accounts classed as skilled in one sample stay skilled in a held-out sample, against about 10% for mutual funds in a parallel test. Skilled traders and market makers (under 3.5% of accounts) capture over 30% of gains. The majority supplies volume and its losses fund the minority.
*Implication:* order flow from identified skilled wallets is a candidate predictor of price changes. It also sets a prior that an LLM agent trading as a taker is on the losing side on average.

**ng2025price** (Ng, Peng, Tao and Zhou, SSRN 2025). Abstract only. Common contracts on Polymarket, Kalshi, PredictIt, and Robinhood before the 2024 election. Liquid prediction markets beat polls, with significant cross-platform price gaps. Polymarket leads Kalshi in price discovery, most strongly when liquidity and activity are high. Net order imbalance from large trades predicts subsequent returns.
*Implication:* test lead-lag between Polymarket and Kalshi on matched contracts in 2025-2026, after Kalshi's volume overtook Polymarket's.

**tsang2026anatomy** (Tsang and Yang, arXiv 2603.03136). Abstract only. Complete on-chain settlement data for Polymarket's 2024 presidential markets. Naive volume overstates turnover because ordinary trades can mint outcome shares. October Trump-market turnover was $391 million against $958 million naive volume. Moving the October forecast by five percentage points required $9.1 million after correction, against $15.6 million naive. The measurement problem affects 249 markets.
*Implication:* our liquidity and price-impact variables for Polymarket need the mint/merge correction. Depth is shallower than reported volume suggests.

**sirolly2025network** (Sirolly, Ma, Kanoria and Sethi, SSRN November 2025). Metadata confirmed; numbers from secondary coverage (Fortune, 2025-11-07). A network-clustering method flags closed clusters of wallets trading among themselves. About 25% of Polymarket volume over three years is estimated to be wash trading, peaking near 60% in December 2024, about 5% in May 2025, and about 20% in early October 2025. 14% of 1.26 million wallets were flagged. The share was 45% in sports and 17% in election markets. The authors describe these as estimates and link the activity to expectations of a token airdrop.
*Implication:* volume-based filters and liquidity proxies on Polymarket need a wash-trade adjustment, especially for sports and for late 2024.

**rasooly2025manipulable** (Rasooly and Rozzi, arXiv 2503.03312). Abstract only. Field experiment with random price shocks in 817 prediction markets and hourly price tracking. Effects of the trades remain visible 60 days later, fading over time. Markets with more traders, more volume, and an external probability source revert faster.
*Implication:* thin markets do not self-correct quickly. Mispricing in illiquid contracts can persist long enough to trade, and can also persist against us.

---

## B. LLM forecasting vs markets and crowds

**halawi2024approaching** (Halawi, Zhang, Yueh-Han and Steinhardt, arXiv 2402.18563). Full text (HTML). Retrieval-augmented GPT-4 system tested on 914 binary questions published after 1 June 2023 from Metaculus, GJ Open, INFER, Polymarket, and Manifold. System Brier 0.179 against crowd 0.149, accuracy 71.5% against 77.0%. When the crowd is uncertain (0.3 to 0.7) the system scores 0.238 against 0.240. A weighted average with the crowd improves the crowd from 0.149 to 0.146.
*Implication:* the replicable claim is the small ensemble gain (0.003 Brier) from adding an LLM to the market price. Paleka et al. report at least 3.8% of this dataset is trivially answerable in backtest.

**schoenegger2024wisdom** (Schoenegger, Tuminauskaite, Park and Tetlock, arXiv 2402.19379). Abstract only. An ensemble of twelve LLMs on 31 binary questions is statistically indistinguishable from a crowd of 925 human forecasters. Showing GPT-4 and Claude 2 the human median improves their accuracy by 17 to 28%.
*Implication:* small sample (31 questions). The useful result is that conditioning on the crowd helps the model, which is the same direction as market-conditioned prompting.

**karger2024forecastbench** (Karger et al., arXiv 2409.19839). Full text (HTML). Dynamic benchmark of 1,000 automatically generated questions about future events, drawn from four market sources (Polymarket, Metaculus, Manifold, RFI) and five datasets (ACLED, DBnomics, FRED, Wikipedia, Yahoo Finance). On a 200-question human comparison set: superforecasters 0.096 Brier, general public 0.121, best LLM (Claude 3.5 Sonnet) 0.122. Top LLM entries used the crowd forecast on market questions as an input.
*Implication:* the contamination-free design (questions about unresolved events only) is the standard to match. The live leaderboard numbers were not retrieved today.

**paleka2025pitfalls** (Paleka, Goel, Geiping and Tramèr, arXiv 2506.00723). Full text (HTML). Catalogs evaluation failures. Logical leakage: backtest question sets reveal outcomes through question selection (at least 3.8% of Halawi et al. and about 10% of another dataset trivially answerable). Date-restricted search leaks future information. Stated knowledge cutoffs are unreliable. Models can copy human or market forecasts present in their inputs. Benchmark-maximizing forecasters are rewarded for overconfident bets. Brier averages are dominated by mid-probability questions.
*Implication:* this is the checklist for our evaluation design. Forward-only evaluation, no reliance on stated cutoffs, and a market-price baseline in every table.

**yang2025prophet** (Yang et al., arXiv 2510.17638). Full text (HTML). Prophet Arena: 1,367 resolved Kalshi events (72,136 markets), 23 LLMs, cutoff 11 October 2025. Best model Brier 0.184 (plus or minus 0.006) against a market baseline of 0.187 (plus or minus 0.006), a difference inside the error bars. Best models reach ECE of 0.05 or lower against 0.069 for the market. Average return under the paper's betting rule is 0.943 for the best model and 0.899 for the market baseline, both below 1. LLMs lag the market in the final hours before resolution.
*Implication:* LLMs roughly tie the market on Brier and still lose money under a simple betting rule. Forecast accuracy and trading profit must be reported separately.

**nel2025kalshibench** (Nel, arXiv 2512.16030). Abstract only. 300 Kalshi questions resolving after model training cutoffs, five frontier models. All models are overconfident. The best (Claude Opus 4.5) has ECE 0.120. Reasoning-enhanced variants were worse calibrated than their base versions.
*Implication:* raw LLM probabilities need post-hoc calibration before Kelly sizing. Small sample.

**wilson2026futureeval** (Wilson and Bash, Metaculus, 9 September 2026). Page read. Spring 2026 tournament: 173 bots, 297 scored questions, 10 pro forecasters on 99 overlapping questions. Bot-team head-to-head score against pros was -1.25 (95% CI -4.87 to 2.37, p = 0.247), up from -20.03 in Q2 2025, -17.7 in Q1 2025, -8.9 in Q4 2024, and -11.3 in Q3 2024. Pros won 64% of questions. Nine of ten individual pros beat every individual bot.
*Implication:* by mid-2026 the aggregate bot-versus-pro gap is statistically indistinguishable from zero on this benchmark. This is a blog post from the tournament organizer.

**turtel2025outcome** (Turtel et al., arXiv 2505.17989). Abstract only. Reinforcement learning on resolved prediction-market questions with news headlines. A 14-billion-parameter model matches or exceeds frontier models such as o1 on accuracy with better calibration, and a simulated Polymarket trading rule returns over 10%.
*Implication:* a simulated return without order-book execution. Treat as an upper bound to challenge with realistic fills and fees.

**alur2025aia** (Alur et al., arXiv 2511.07678). Abstract only. Agentic search plus a supervisor agent plus statistical calibration. Matches superforecasters on ForecastBench. On a harder benchmark built from liquid prediction markets the system underperforms market consensus alone, and an ensemble of system plus market beats the market.
*Implication:* same pattern as Halawi et al. The LLM adds marginal information when combined with price. Test the ensemble weight out of sample.

**capponi2025agentic** (Capponi, Gliozzo and Zhu, arXiv 2512.02436). Abstract only. An agentic pipeline clusters markets by contract text and finds related pairs before looking at prices. Discovered relations agree with exchange-recorded settlements 62.8% of the time against 40.6% for an NLI baseline. A trading application reports 14.12% net ROI after fees over two months. The abstract as summarized dates the data to 2026 while the paper was first submitted in December 2025, so the sample period needs checking in the PDF.
*Implication:* this is the closest prior work to semantic relationship trading. A two-month window is short. Our version needs a deflated Sharpe ratio and a count of strategies tried.

**cheng2026polybench** (Cheng, Liu and Long, arXiv 2604.14199). Abstract only. 38,666 binary Polymarket markets across 4,997 events with synchronized order-book and news snapshots, 36,165 predictions from seven LLMs between 6 and 12 February 2026. Two models had positive confidence-weighted return (17.6% and 6.2%) and five lost money.
*Implication:* one week of data. Useful as a design reference for timestamp-locked evaluation, weak as evidence of profitability.

**kim2026riskmanager** (Kim et al., arXiv 2602.07048). Abstract only. Two-stage lead-lag discovery on Kalshi economics markets: Granger screening, then an LLM judges whether a plausible transmission mechanism exists. Win rate rises from 51.4% to 54.5% and average losing trade falls from $649 to $347.
*Implication:* the LLM acts as a filter on statistically mined pairs. This is a cheap ablation for our relationship-discovery experiments.

**lopezlira2025memorization** (Lopez-Lira, Tang and Zhu, arXiv 2504.14765). Abstract only. LLMs recall exact pre-cutoff economic and financial values. Instructions to respect a historical cutoff and masking both fail to prevent recall. No recall occurs for post-cutoff data. Forecasting skill is not identified inside the training window.
*Implication:* any backtest of an LLM on markets that resolved before its cutoff is uninterpretable. Evaluate only on post-cutoff resolutions.

**sarkar2024lookahead** (Sarkar and Vafa, SSRN 2024). Abstract only. Direct tests for lookahead bias based on events that should be unpredictable from a given information set. Finds lookahead bias in predicting risk factors from earnings calls and election winners from candidate biographies. Prompting does not reliably remove it.
*Implication:* gives a test design we can reuse: check whether the model "predicts" outcomes that were unpredictable at the time.

---

## C. Prediction markets and asset prices

**wolfers2016financial** (Wolfers and Zitzewitz, Brookings, October 2016). Page read. Event study of the 26 September 2016 debate. Clinton's Betfair price rose from 63 to 69 cents while S&P 500 futures rose 0.71%. Scaling up, markets implied US equities worth about 12% more under Clinton, 15 to 30% lower expected volatility, an oil price about $4 higher, and Treasury yields about 25 basis points higher. The sign for equities was the opposite of the historical Republican premium.
*Implication:* the template for mapping a change in event probability to an asset-price response. The ratio of asset move to probability move is the estimand.

**snowberg2007partisan** (Snowberg, Wolfers and Zitzewitz, QJE 2007). Abstract only. Uses flawed exit polls on election day 2004 and the vote count as exogenous shocks to the expected winner. Markets expected higher equity prices, interest rates, oil prices, and a stronger dollar under Bush. Across elections since 1880, a Republican win raises equity valuations by 2 to 3%.
*Implication:* identification by high-frequency exogenous probability shocks. We need comparable clean shocks (debates, court rulings, data releases) for 2024-2026.

**knight2006policy** (Knight, Journal of Public Economics 2006). Abstract only (IDEAS). 70 politically sensitive firms in the 2000 election, daily returns regressed on Iowa market probabilities. Bush-favored firms were worth 3% more and Gore-favored firms 6% less under a Bush administration, a 9% differential.
*Implication:* a cross-sectional design. Sort stocks by exposure to an event and regress returns on prediction-market probability changes.

**wolfers2009iraq** (Wolfers and Zitzewitz, Economica 2009). Abstract only. Uses a contract on Saddam Hussein's ouster. A 10% rise in the probability of war came with a $1 rise in spot oil and a 1.5% fall in the S&P 500. Option prices implied a negatively skewed distribution of war outcomes.
*Implication:* geopolitical contracts map into oil and equities. The same design applies to 2026 Iran and Venezuela markets, with the insider-trading caveat in section F.

**diercks2026kalshi** (Diercks, Katz and Wright, NBER WP 34702 and FEDS 2026-010). PDF pages 1 to 9 read. Kalshi macro contracts (CPI, core CPI, unemployment, payrolls, GDP, fed funds target by meeting) since 2021-2022. For the fed funds rate 150 days ahead, Kalshi's mean absolute error is very similar to the New York Fed's Survey of Market Expectations. The Kalshi median and mode have a perfect record on the day before FOMC meetings, a statistically significant improvement over the fed funds futures forecast. Kalshi matches the Bloomberg consensus for core CPI and unemployment and significantly improves on it for headline CPI. Variance of the implied rate distribution falls after data releases, and positive CPI surprises move the implied mean more than negative ones. The paper notes Kalshi position limits of up to $7 million per market and names Susquehanna, Citadel, and Two Sigma as liquidity providers.
*Implication:* the central finance-facing claim to replicate: compare Kalshi-implied and futures-implied rate paths meeting by meeting and test whether the gap is a risk premium in futures or noise in Kalshi.

**gurkaynak2006macro** (Gürkaynak and Wolfers, NBER WP 11929). Abstract only. Economic Derivatives auctions (launched 2002) on macro data releases. Market-based expectations are similar to survey forecasts and predict financial-market reactions to surprises somewhat better. Implied densities are well calibrated. Little evidence that risk aversion drives a wedge between prices and probabilities in that market.
*Implication:* the pre-Kalshi precedent. A small risk premium in short-dated macro event contracts is the null to test.

**swanson2025effects** (Swanson, Wang and Wu, December 2025 draft). PDF pages 1 to 2 read. Uses intraday Kalshi macro contracts to measure how FOMC announcements move market-implied macro expectations. Results fit standard monetary transmission, with little or no role for a Fed information effect.
*Implication:* shows Kalshi contracts are usable as high-frequency expectation measures in event studies. Our asset-price experiments can use the same windows.

**eichengreen2025pressure** (Eichengreen, Viswanath-Natraj, Wang and Wang, SSRN 2025). Metadata only. Title, authors, and year confirmed. Per a search snippet of the VoxEU column (not opened), the paper uses Polymarket contracts on Fed decisions and on Chair Powell's removal and links statements questioning Fed independence to expected short rates and long yields. Not read.
*Implication:* likely the closest existing paper on Polymarket odds and rates. Read before writing section C.

**mohanty2026kalshi** (Mohanty and Krishnamachari, arXiv 2604.01431). Abstract only. Ten Kalshi macro series and six crypto assets, January 2023 to March 2026. Fed repricing on KXFED predicts Bitcoin volatility in sample (t = 3.63), dependent on the 2024-2025 cutting cycle. Recession repricing gives an MSFE ratio of 0.979 (Clark-West p = 0.020). CPI repricing predicts altcoin volatility, with out-of-sample gains for Ethereum (MSFE ratio 0.959, p = 0.010). Two specifications survive Benjamini-Hochberg at q = 0.05.
*Implication:* small out-of-sample gains (2 to 4% MSFE) with explicit multiple-testing control. A realistic effect-size prior for our cross-asset tests.

---

## D. Binary options, risk-neutral vs physical probability

**breeden1978prices** (Breeden and Litzenberger, Journal of Business 1978). Abstract only. The price of a $1 claim paid if the underlying ends between two levels is given by the second partial derivative of the call price with respect to strike.
*Implication:* the formula for extracting option-implied threshold probabilities to compare with prediction-market threshold contracts. Crossref lists only the first page (621), so confirm the page range before submission.

**jackwerth2000recovering** (Jackwerth, RFS 2000). Abstract only. Derives implied risk-aversion functions from S&P 500 option-implied (risk-neutral) and realized (subjective) distributions. After the 1987 crash the implied functions become partly negative and increasing, which the paper attributes to option mispricing, and simulated strategies exploiting it earn excess returns.
*Implication:* the wedge between risk-neutral and physical probabilities is large and state dependent in index options. An option-implied probability is a biased benchmark for a physical event probability.

**ross2015recovery** (Ross, Journal of Finance 2015). Abstract only. State prices are the product of the pricing kernel and natural probabilities. Under the paper's assumptions the two can be separated from state prices alone.
*Implication:* a formal statement of what must be assumed to turn option prices into physical probabilities. Cite when discussing why a Polymarket-versus-options gap need not be an arbitrage.

**portnaya2026prediction** (Portnaya, arXiv 2606.19517). Abstract only. Compares Polymarket Yes prices on Bitcoin threshold contracts with the discounted risk-neutral binary value implied by Binance options at the same strike and maturity. Mean gap 5.6 percentage points over 214 hourly observations in the main September 2023 contract, 6.3 points pooled over three markets (287 observations), and 11 points using Deribit. The gap is persistent with an AR(1) half-life near four hours and mean reverting, and is larger at low implied probabilities and long maturities.
*Implication:* the direct precedent for our crypto threshold experiment. The sample is tiny (three markets from 2023). A 2025-2026 replication across hundreds of daily and weekly threshold contracts would be new.

---

## E. Backtest rigor, scoring rules, calibration

**bailey2014deflated** (Bailey and López de Prado, JPM 2014). Abstract only. The deflated Sharpe ratio corrects a reported Sharpe ratio for the number of trials and for non-normal returns.
*Implication:* log every strategy variant tried and report DSR next to raw Sharpe.

**bailey2016probability** (Bailey, Borwein, López de Prado and Zhu, Journal of Computational Finance). Abstract only. Defines the probability of backtest overfitting and estimates it with combinatorially symmetric cross-validation. Standard hold-out is unreliable for strategy selection.
*Implication:* apply CSCV to the strategy grid. Crossref has no volume or pages for this entry.

**harvey2016cross** (Harvey, Liu and Zhu, RFS 2016). Abstract only. A multiple-testing framework over the factor literature since 1967. A new factor needs a t-statistic above 3.0, and most claimed findings are likely false.
*Implication:* use t > 3 as the bar for any signal we report as a discovery.

**white2000reality** (White, Econometrica 2000). Abstract only. A bootstrap test of whether the best model found in a specification search beats a benchmark, accounting for the search.
*Implication:* the test for "best of N strategies beats buy-at-market".

**hansen2005test** (Hansen, JBES 2005). Abstract only. The SPA test studentizes the statistic and uses a sample-dependent null, which gives more power than the reality check and less sensitivity to poor alternatives.
*Implication:* prefer SPA over the reality check when the strategy set contains many weak variants.

**gu2020empirical** (Gu, Kelly and Xiu, RFS 2020). Abstract only. Trees and neural networks roughly double the performance of leading regression-based return forecasts in some cases, driven by nonlinear interactions. Momentum, liquidity, and volatility are the dominant signals across methods.
*Implication:* the reference protocol for out-of-sample ML evaluation in asset pricing, including rolling training and validation splits.

**kelly1956new** (Kelly, Bell System Technical Journal 1956). Abstract only. A gambler with side information can grow capital exponentially at a maximum rate equal to the channel's information rate, with a generalization to arbitrary odds.
*Implication:* justifies log-growth (Kelly) sizing. Use fractional Kelly given the calibration errors documented in section B.

**gneiting2007strictly** (Gneiting and Raftery, JASA 2007). Abstract only. Theory of strictly proper scoring rules, including logarithmic, quadratic (Brier), spherical, and CRPS.
*Implication:* report both Brier and log scores. Log score penalizes confident misses that Brier underweights.

**murphy1973new** (Murphy, Journal of Applied Meteorology 1973). Abstract only. Partitions the Brier score into uncertainty, reliability, and resolution.
*Implication:* report the three-term decomposition by domain and horizon so that calibration and discrimination are separated.

**brier1950verification** (Brier, Monthly Weather Review 1950). Metadata only (no abstract in the registry). Cited as the origin of the Brier score.
*Implication:* cite for the definition only.

**niculescu2005predicting** (Niculescu-Mizil and Caruana, ICML 2005). Abstract only. Boosted trees and SVMs push probabilities away from 0 and 1, naive Bayes pushes toward them. Platt scaling and isotonic regression correct these distortions, with different data requirements.
*Implication:* covers both Platt and isotonic calibration for our recalibration step. Fit on a time-ordered holdout.

**benjamini1995controlling** (Benjamini and Hochberg, JRSS-B 1995). Abstract only. Defines the false discovery rate and a step-up procedure controlling it for independent tests.
*Implication:* apply across the grid of domain-by-horizon and cross-asset tests.

**diebold1995comparing** (Diebold and Mariano, JBES 1995). Abstract only. Tests of equal predictive accuracy for two forecasts under general loss functions and serially correlated errors.
*Implication:* the test for LLM versus market Brier differences. Cluster by event, since contracts in one event are dependent.

---

## F. Information and news in markets

**croxson2014information** (Croxson and Reade, Economic Journal 2014). Abstract only. High-frequency Betfair data around goals scored at the cusp of half-time, where trading pauses give clean identification. Prices update swiftly and fully.
*Implication:* the efficient benchmark for news incorporation in a liquid betting exchange. Our drift tests compare against it.

**brown2019when** (Brown, Reade and Vaughan Williams, IJF 2019). Abstract only (IDEAS). Intrade prices around poll releases. Poll releases trigger a jump in trading by relatively inexperienced traders, and price efficiency falls right after the release.
*Implication:* news arrival can lower informativeness for a short window. Test whether post-news windows on Polymarket show worse calibration.

**tsang2026political** (Tsang and Yang, arXiv 2603.03152). Abstract only. Polymarket transaction data around three 2024 shocks. Trading surges after each, mostly from experienced traders with larger positions. The debate price move largely reversed, the assassination-attempt repricing held, and Biden's withdrawal produced the most volume with little change in Trump's price.
*Implication:* volume and price response are different objects. Reversal after some shocks is evidence of overreaction, in contrast to the underreaction theory in ottaviani2015price.

**mitts2026iran** (Mitts and Ofir, SSRN 2026). Abstract only. Case studies of apparent trading on material nonpublic information on Polymarket and Kalshi, from the February 2026 US-Israel strike on Iran to a celebrity engagement. A screen of all Polymarket markets from February 2024 to February 2026 flags over 210,000 suspicious wallet-market pairs. Flagged traders have a 69.9% win rate and about $143 million in aggregate anomalous profit. The paper argues CFTC Rule 180.1 is narrower than SEC Rule 10b-5.
*Implication:* informed flow is large in geopolitical markets. Price moves before public news may reflect leaks, which contaminates any "market led the news" result.

**nechepurenko2026permarket** (Nechepurenko, arXiv 2605.02287). Abstract only. Compares three approaches to detecting informed trading on Polymarket: the Mitts-Ofir screen, the Gomez-Cram et al. sign-randomization test (3.14% of accounts skilled, 1,950 accounts flagged as possible insiders), and a per-market information leakage score. Argues they measure different things. Uses the Van Dyke case as an example where the layers combine.
*Implication:* skilled and insider are separate labels. Our wallet-level features should keep them apart.

**sultan2026conversation** (Sultan and Morstatter, arXiv 2609.28965). Abstract only. 79 non-political Polymarket markets. Comment attention predicts heavy trading within 18 hours about as well as trading history (PR-AUC 0.786 against 0.790). Adding attention, sentiment, and stance to flow history raises ROC-AUC for buying direction from 0.780 to 0.788. Stance shifts against the leading outcome before reversals in 23 of 27 markets. The authors state the associations are predictive and not causal.
*Implication:* on-platform text adds little beyond order flow (0.008 AUC). A realistic prior for any social-media signal.

---

## Verified but left out of refs.bib

These were opened and confirmed today and dropped only to keep the bib near 70 entries. Add them if needed.

- Rothschild (2009), "Forecasting Elections", POQ 73(5), 895-916. https://doi.org/10.1093/poq/nfp082
- Rhode and Strumpf (2004), "Historical Presidential Betting Markets", JEP 18(2), 127-142. https://doi.org/10.1257/0895330041371277
- Arrow et al. (2008), "The Promise of Prediction Markets", Science 320(5878), 877-878. https://doi.org/10.1126/science.1157679
- Thaler and Ziemba (1988), "Anomalies: Parimutuel Betting Markets", JEP 2(2), 161-174. https://doi.org/10.1257/jep.2.2.161
- Wolfers and Zitzewitz (2006), "Prediction Markets in Theory and Practice", NBER WP 12083. https://doi.org/10.3386/w12083
- Cutting et al. (2025), "Are Betting Markets Better than Polling in Predicting Political Elections?", arXiv 2507.08921
- Dahlke et al. (2026), "Electoral Predictions on Polymarket", Journal of Quantitative Description: Digital Media 6. https://doi.org/10.51685/jqd.2026.011 (778,634 accounts, 30.5 million trades, $5.86 billion; 90.2% of joint trade-comment pairs are trade-first)
- Zou et al. (2022), "Forecasting Future World Events with Neural Networks" (Autocast), arXiv 2206.15474
- Dai, Teehan and Ren (2024), "Are LLMs Prescient?" (Daily Oracle), arXiv 2411.08324
- Wildman et al. (2025), "Bench to the Future", arXiv 2506.21558
- Paleka et al. (2024), "Consistency Checks for Language Model Forecasters", arXiv 2412.18544
- Arora and Malpani (2026), "PredictionMarketBench", arXiv 2602.00133
- Kim et al. (2026), "Forecasting Future Language: Context Design for Mention Markets", arXiv 2602.21229
- Glasserman and Lin (2023), "Assessing Look-Ahead Bias in Stock Return Predictions Generated by GPT Sentiment Analysis", arXiv 2309.17322
- Guo et al. (2017), "On Calibration of Modern Neural Networks", arXiv 1706.04599
- Zadrozny and Elkan (2002), "Transforming Classifier Scores into Accurate Multiclass Probability Estimates", KDD. https://doi.org/10.1145/775047.775151
- Sullivan, Timmermann and White (1999), "Data-Snooping, Technical Trading Rule Performance, and the Bootstrap", JF 54(5), 1647-1691. https://doi.org/10.1111/0022-1082.00163
- Bliss and Panigirtzoglou (2004), "Option-Implied Risk Aversion Estimates", JF 59(1), 407-446. https://doi.org/10.1111/j.1540-6261.2004.00637.x
- Tetlock (2007), "Giving Content to Investor Sentiment", JF 62(3), 1139-1168. https://doi.org/10.1111/j.1540-6261.2007.01232.x
- Brown, Rambaccussing, Reade and Rossi (2018), "Forecasting with Social Media: Evidence from Tweets on Soccer Matches", Economic Inquiry 56(3), 1748-1763. https://doi.org/10.1111/ecin.12506 (13.8 million tweets; tweet tone carries information not in Betfair prices, mainly right after goals and red cards)
- Dalen (2025), "Toward Black Scholes for Prediction Markets", arXiv 2510.15205
- Angelini (2026), "The Shape of Macroeconomic Beliefs", arXiv 2606.30040
- Bhaskara and Jerfy (2026), "Public Opinion as an Option", arXiv 2609.14267
- Rahman, Al-Chami and Clark (2025), "SoK: Market Microstructure for Decentralized Prediction Markets", arXiv 2510.15612
- Nechepurenko (2026), arXiv 2605.00459 and arXiv 2605.00493 (information leakage score papers)
- Hanson, Oprea and Porter (2006), "Information Aggregation and Manipulation in an Experimental Market", JEBO 60(4), 449-459. https://doi.org/10.1016/j.jebo.2004.09.011 (metadata only, no abstract available)
- Bernard and Thomas (1989), "Post-Earnings-Announcement Drift: Delayed Price Response or Risk Premium?", Journal of Accounting Research 27. https://doi.org/10.2307/2491062 (metadata only, no abstract available)

## Unverified leads

Not in refs.bib. Each needs to be opened and read before use.

- Platt (1999), "Probabilistic Outputs for Support Vector Machines and Comparisons to Regularized Likelihood Methods". Listed in OpenAlex without a DOI. No source page opened.
- Rhode and Strumpf (2006), "Manipulating Political Stock Markets: A Field Experiment and a Century of Observational Data". Listed in OpenAlex as a RePEc working paper. Not opened.
- Yicheng Yang, "Pricing Prediction Markets: Risk Premiums, Incomplete Markets, and a Decomposition Framework". Appears only as an attachment to a CFTC comment letter in search results (291,309 contracts across six platforms, per the snippet). No paper page found.
- An unnamed study reported by Crypto Briefing (https://cryptobriefing.com/polymarket-repricing-lag-80-minutes/) claiming Polymarket takes about 80 minutes to fully reprice after major news, with an initial response coefficient of 0.64. The article names no authors, title, or venue.
- University of Gothenburg thesis, "Prediction Markets vs Futures Markets: Information Efficiency in FOMC Rate Expectations" (Polymarket against CME FedWatch over 26 FOMC meetings, February 2023 to March 2026, per the search snippet). The repository page blocked access.
- Dune blog post "Pricing the Fed: Kalshi, Polymarket, CME FedWatch". Search snippet reports a persistent gap of about 20 cents on "no change" contracts months before meetings, converging to within 1 cent by decision day. The URL returned 404.
- Alex McCullough's Dune dashboard on Polymarket accuracy (about 90% one month out, 94% four hours out), known only through CryptoPotato coverage.
- Reichenbach and Walther numbers (124 million trades, $48 billion) from a press snippet. The paper itself is in refs.bib as metadata only.
- Eichengreen et al. findings, from a VoxEU search snippet. The paper is in refs.bib as metadata only.
- Roosevelt Institute report on Kalshi trader losses (July 2026). Only press coverage was opened. See the news section.
- Anti-Corruption Data Collective report on military-market wallets (August 2026). Only the Reuters story (via Al-Monitor) was opened.
- Phan et al. (2024) and Tao et al. (2025), LLM forecasting papers critiqued in paleka2025pitfalls. Not opened.
- Stevens Institute seminar "Event Contract Mispricing via Options-Implied Probabilities" (May 2025). Seminar listing only.
- ForecastBench live leaderboard values. The landing page did not expose numbers to the fetch tool.

---

## Recent market-structure news (2025-2026)

Dates are event dates where the source gives one. Each item lists the page that was opened. Items marked "snippet" come from search-result text and were not opened.

### Polymarket: US re-entry, funding, fees

- **July 2025.** Polymarket bought CFTC-licensed exchange and clearinghouse QCEX for $112 million. Source: Decrypt, 2025-11-25, https://decrypt.co/350003/polymarket-set-us-return-following-approval-cftc
- **September 2025.** CFTC cleared Polymarket's return to the US after its 2022 exit. Source: Yogonet, 2026-01-05, https://www.yogonet.com/international/news/2026/01/05/116954-polymarket-misses-2025-public-us-release-after-reentry-approval
- **7 October 2025.** Intercontinental Exchange announced a $2 billion investment in Polymarket at a $9 billion post-money valuation. Source: The Block, https://www.theblock.co/post/373641/nyse-parent-firm-ice-eyes-2-billion-investment-in-polymarket-wsj
- **25 November 2025.** CFTC issued an Amended Order of Designation allowing Polymarket to run an intermediated US exchange and onboard brokers and customers directly. Source: Decrypt, same URL as above.
- **End of 2025.** The US app was still invite-only from a waitlist and missed the NFL season. Source: Yogonet, same URL as above. Snippet (AffPapa, not opened): a public US iOS app launched 12 May 2026.
- **January to March 2026: fees on the international exchange.** Taker fees started on 15-minute crypto markets on 5 January 2026, reached sports on 18 February, all crypto timeframes on 6 March, and nearly all other categories on 30 March. Source: Pine Analytics, 2026-03-25, https://pineanalytics.substack.com/p/polymarket-fee-rollout. That post estimated about $160 million in daily taker volume and about $1.2 million in gross daily fees, and reported no visible volume drop in sports.
- **Current fee schedule (read 2026-10-02).** fee = C x feeRate x p x (1 - p), where C is shares and p is price. Taker rates: crypto 0.07; sports, economics, culture, weather, other 0.05; finance, politics, mentions, tech 0.04; geopolitics 0. Makers pay nothing, and 15 to 25% of fees fund maker rebates by category. Source: https://docs.polymarket.com/trading/fees. At p = 0.5 this is 1.75, 1.25, and 1.0 cents per share. The Pine Analytics peak rates from March (for example sports 0.75%) do not match this schedule, so the schedule changed after launch. A search snippet listed sports at 0.03 under "Fee Structure V2". Backtests need a dated fee table.
- **Polymarket US fees.** Same formula, taker rates effective 1 July 2026: geopolitics 0, politics/finance/tech/mentions 4%, sports/economics/culture/weather/other 5%, crypto 7%. Makers pay nothing. Source: River Markets, updated 2026-08-09, https://www.rivermarkets.com/insights/polymarket-us-fees.html. Snippet (CFTC rule filing, not opened): the standard taker coefficient moved from 0.06 to 0.0695 effective 17 September 2026.
- **Funding.** Snippets (KuCoin, The Block, not opened): Polymarket sought new funding at a $12 to $15 billion valuation, and its CMO confirmed plans for a POLY token and airdrop in October 2025.

### Kalshi: growth, sports, funding

- **7 May 2026.** Kalshi raised $1 billion (Series F, led by Coatue) at a $22 billion valuation. The company reported annualized volume rising from $52 billion to $178 billion and more than 90% of US prediction-market activity. Industry volume in March 2026 was $25.7 billion, of which sports $10.1 billion and crypto $7.3 billion. Source: The Block, https://www.theblock.co/post/400413/kalshi-hits-22-billion-valuation-after-1-billion-raise-led-by-coatue
- **24 June 2026.** Kalshi in talks to raise at a $40 billion valuation. June-to-date volume was $21.1 billion for Kalshi against about $9.7 billion for Polymarket plus Polymarket US. Annualized revenue above $2 billion (per The Information). Source: The Block, https://www.theblock.co/post/406061/kalshi-40-billion-valuation
- **Sports share.** Sports were 87% of Kalshi volume in 2025 and 72% in 2026 through 30 August. Source: Front Office Sports, 2026-08-30, https://frontofficesports.com/article/what-kalshis-big-court-loss-means-for-prediction-markets/. Becker's sample (through November 2025) has sports at 72% of volume. A search snippet gave 65%. The figure depends on the window.
- **August 2026.** Combined Kalshi and Polymarket volume fell 14.5% to $45.33 billion (Kalshi $37.17 billion, Polymarket plus US $8.16 billion) from $52.99 billion in July (Kalshi $40.1 billion, Polymarket $12.89 billion), the first monthly decline in a year. Source: KuCoin News citing The Block data, 2026-09-02, https://www.kucoin.com/news/flash/kalshi-and-polymarket-august-trading-volume-drops-14-5-for-first-monthly-decline-in-a-year
- **March 2026.** Kalshi's market on Ali Khamenei leaving office closed in dispute because the contract title and the rules pointed to different resolutions. Kalshi absorbed a $2.2 million loss. Source: CDC Gaming, https://cdcgaming.com/brief/kalshis-botched-khamenei-market-could-be-a-problem-for-its-wall-street-ambitions/
- **July 2026.** A Roosevelt Institute analysis of 400 million Kalshi trades (July 2021 to May 2026) estimated takers lost $583.5 million to makers. Kalshi disputed it, saying the study equates taker with casual and maker with professional. Sources: Casino.org, 2026-07-13, https://casino.org/news/kalshi-rebuffs-think-tank-claim-regular-traders-lost-584-million-on-platform and The American Prospect, 2026-08-26, https://prospect.org/2026/08/26/house-always-wins-kalshi-prediction-markets/. The Prospect piece also reports that Kalshi's data partner Dune took the underlying data down and later offered it behind a $40,000 paywall. This matters for data access in our project.
- **28 January 2026.** Press coverage of the Diercks, Katz and Wright paper: Kalshi had a perfect day-before record on FOMC decisions from 2022 through June 2025. Source: Fortune, https://fortune.com/2026/01/28/kalshi-prediction-market-federal-reserve-betting-forecast-nber-working-paper/

### CFTC and the courts

- **12 March 2026.** CFTC published an Advance Notice of Proposed Rulemaking on prediction markets, asking how core principles apply to event contracts and which contracts may be contrary to the public interest. Comments were due 45 days after Federal Register publication. Source: CFTC release 9194-26, https://www.cftc.gov/PressRoom/PressReleases/9194-26. Snippets (law-firm alerts, not opened): the CFTC withdrew a prior proposed event-contract rule in February 2026 and received over 1,500 comments on the ANPRM.
- **6 April 2026.** Third Circuit, KalshiEX LLC v. Flaherty (No. 25-1922), 2-1: affirmed a preliminary injunction against New Jersey, holding that sports event contracts on a CFTC-registered exchange are swaps and that the Commodity Exchange Act likely preempts state gambling law. Preliminary-injunction stage only. Source: Holland and Knight, https://www.hklaw.com/en/insights/publications/2026/04/federal-appeals-court-cftc-jurisdiction-over-sports-event-contracts
- **Late August 2026.** Ninth Circuit panel ruled that Nevada can enforce its gambling laws against Kalshi's sports contracts, creating a circuit split. The ruling also applies to Robinhood and Crypto.com cases. Source: Front Office Sports, 2026-08-30, URL above.
- **Late September 2026.** Sixth Circuit ruled unanimously against Kalshi, finding it failed to show its sports contracts are swaps under CFTC jurisdiction, so Ohio and Tennessee can regulate them. The split is now two circuits to one against Kalshi and a Supreme Court petition is expected. Source: Cointelegraph, https://cointelegraph.com/news/kalshi-loses-appeal-setting-up-potential-supreme-court-case (the article gives 26 September, which falls on a Saturday, so the ruling date needs checking).

### Insider trading and manipulation episodes

- **6 November 2025.** Columbia study estimated about 25% of Polymarket volume over three years was wash trading. See sirolly2025network. Source: Fortune, 2025-11-07, https://fortune.com/2025/11/07/polymarket-wash-trading-inflated-prediction-markets-columbia-research/
- **25-26 February 2026.** Kalshi announced its first two insider-trading disciplinary cases. An editor for YouTuber MrBeast (Artem Kaptur) traded about $4,000 on related markets with near-perfect success and received a $20,000 fine and a two-year suspension. Kyle Langford, a California gubernatorial candidate, bet on his own candidacy. Both were referred to the CFTC. Source: Decrypt, https://decrypt.co/359264/mrbeast-video-editor-suspended-kalshi-insider-trading
- **22 April 2026.** Kalshi disciplined three political candidates for trading on their own races (five-year suspensions, penalties of $539.85 to $6,229.30). Source: Lowenstein Sandler, https://lowenstein.com/news-insights/publications/client-alerts/cftc-and-kalshi-announce-enforcement-actions-targeting-prediction-markets-fctm
- **23-24 April 2026.** DOJ unsealed an indictment of Army Special Forces Master Sergeant Gannon Ken Van Dyke for using classified information about the operation to capture Nicolás Maduro (3 January 2026) to bet on Polymarket, with profits of about $400,000. The CFTC filed a parallel civil complaint, its first insider-trading case over event contracts. Sources: Military Times, 2026-04-24, https://www.militarytimes.com/news/your-military/2026/04/24/us-soldier-charged-with-making-400000-on-maduro-removal-bets/ and Lowenstein Sandler, URL above.
- **February 2024 to February 2026.** Mitts and Ofir flag over 210,000 suspicious wallet-market pairs on Polymarket with about $143 million in anomalous profit. See mitts2026iran.
- **20 August 2026.** The Anti-Corruption Data Collective reported 152 Polymarket wallets with an average 97.2% win rate on military and defense markets and $8 million in combined profit, out of 556 wallets that opened, placed a large longshot bet, and cashed out. Polymarket said it has referred dozens of wallets to authorities. Source: Reuters via Al-Monitor, https://al-monitor.com/originals/2026/08/exclusive-more-150-polymarket-wallets-may-have-traded-military-secrets-research
- **Snippet (Public Gaming, not opened):** Kalshi flagged over 50 traders and Polymarket over 90 in 2026, while the CFTC had brought actions against three people.

### What the news implies for the experiments

- Fees turned on in 2026. Any strategy backtested on pre-2026 Polymarket data at zero fees must be re-run with the dated schedule. At p = 0.5 the taker fee is 1.0 to 1.75 cents per share, or 2 to 3.5% of the price paid. For scale, the average taker shortfall Becker measures on Kalshi is 1.12% per trade.
- Volume is concentrated in sports (roughly 65 to 87% on Kalshi depending on the window), and sports contracts face state-level legal risk after the Ninth and Sixth Circuit rulings. Sample composition will shift if sports contracts are pulled in some states.
- Geopolitical markets carry documented insider flow and are fee-free on Polymarket. Lead-lag results there are confounded by leaks.
- Wash trading and mint-based volume inflation mean Polymarket volume overstates liquidity. Use the corrections in tsang2026anatomy and sirolly2025network.
- Kalshi trade data access through Dune changed in mid-2026. Confirm the data source and license before depending on it.
