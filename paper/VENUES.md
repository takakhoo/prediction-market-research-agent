# Venue shortlist: prediction-market efficiency paper

Compiled 2026-10-02. Window considered: submission deadlines after 2026-10-02 and before about 2027-06-30.

How to read the dates:

- A date with a link was read on that official page on 2026-10-02.
- "Not yet announced" means no official page stated the date on 2026-10-02. The date next to it is last year's deadline, labeled as an estimate.
- AoE means Anywhere on Earth (UTC-12). An AoE deadline of day D ends at 12:00 UTC on day D+1, which is 07:00 EST or 08:00 EDT.
- Most pages were read through a fetch tool that summarizes the page. Recheck each date on the linked page before planning around it.

## Recommendation

**Primary: ACM EC 2027** (ACM Conference on Economics and Computation). Deadline not yet announced. Estimate from EC'26: abstract early February 2027, paper about one week later.

**Backup: KDD 2027 Research Track, Cycle 2.** The official call names a "February 2027 deadline" for the second cycle without exact dates.

**If both miss: ICAIF 2027** (ACM International Conference on AI in Finance). Not announced. ICAIF'26 closed on 9 August 2026, so the 2027 deadline will probably fall outside the window, around August 2027.

Reasoning:

1. Fit. The paper's main result is an empirical answer to an economics question: are Polymarket prices calibrated, where do they fail, and does a learned model beat the price after fees. EC is where the prediction-market literature in computer science lives, and the EC'26 topic list includes "Blockchain and cryptocurrencies", "Crowdsourcing and information elicitation", "Econometrics", and "Economic aspects of neural networks and large language models". At ICML or KDD, reviewers score method novelty first, and a walk-forward recalibration model is a modest method contribution. EC reviewers will read the calibration atlas and the efficiency tests as the contribution.
2. Format. EC allows 18 pages of single-column body text plus appendices. A calibration atlas, a pricing model, cost-aware backtests, and cross-market links will not fit comfortably in 8 double-column pages.
3. Journal option stays open. EC lets accepted authors publish only a one-page abstract in the proceedings, and allows simultaneous submission to a journal. The reference list for this paper is mostly economics and finance journals, so keeping a later journal version possible has real value.
4. Timing. The repository holds literature notes and a bib file today. An early February deadline leaves about four months for data work and writing. TheWebConf (25 October) is too soon, and IJCAI (11 January) is three to four weeks tighter than EC.
5. Odds. My estimate, based on no official statistic: EC accepts roughly a quarter of submissions overall, and a careful empirical paper from a single MS author with no theory component probably sits below that average, perhaps 10 to 20 percent. KDD research track odds are similar or slightly lower because of the novelty criterion. ICAIF is the venue where this paper has the best odds, which is why it is the fallback even though it is outside the window.

EC and KDD Cycle 2 will likely have deadlines within a week of each other, and neither allows a concurrent submission to another archival conference. Pick one in January. Choose KDD if the learned pricing model turns out to be the strongest part of the paper. Choose EC if the efficiency and calibration findings are.

Risk with the primary: no EC'27 website, location, or call exists yet. `ec27.sigecom.org` does not resolve and [sigecom.org](https://sigecom.org/) carries no announcement. EC has run every year, so the risk is a shifted date, and the kit may change slightly.

## Ranked shortlist

| # | Venue | Abstract deadline | Paper deadline | Body page limit | Double-blind | arXiv allowed |
|---|-------|-------------------|----------------|-----------------|--------------|---------------|
| 1 | ACM EC 2027 | not yet announced (est. early Feb 2027) | not yet announced (est. ~9 Feb 2027) | 18, single column (EC'26) | yes (EC'26) | yes (EC'26) |
| 2 | KDD 2027 Research, Cycle 2 | "February 2027", day not announced | "February 2027", day not announced | 8 content pages | yes | yes |
| 3 | ICML 2027 | not yet announced (est. ~23 Jan 2027) | not yet announced (est. ~28 Jan 2027) | 8 (ICML 2026) | yes (2026) | yes (2026) |
| 4 | IJCAI 2027 | 4 Jan 2027, 23:59 AoE | 11 Jan 2027, 23:59 AoE | 7 + 2 refs (2026 rule) | yes (2026) | yes (2026) |
| 5 | TheWebConf 2027 | 18 Oct 2026 AoE | 25 Oct 2026 AoE | 8, max 12 total | yes | yes |
| 6 | UAI 2027 | none in 2026 | not yet announced (est. ~25 Feb 2027) | 8 (UAI 2026) | yes (2026) | yes (2026) |
| 7 | NeurIPS 2027 | not yet announced (est. early May 2027) | not yet announced (est. early May 2027) | not checked | not checked | not checked |
| 8 | ICLR 2027 workshops | n/a | suggested 1 Feb 2027 | set per workshop | set per workshop | set per workshop |
| 9 | ICAIF'26 workshops | n/a | 12 Oct 2026, 23:59 AoE | set per workshop | set per workshop | set per workshop |
| 10 | ICAIF 2027 (outside window) | n/a | not yet announced (est. early Aug 2027) | 8 total incl. refs (ICAIF'26) | yes (2026) | yes (2026) |

### 1. ACM EC 2027 (ACM Conference on Economics and Computation)

- Official URL: no EC'27 site yet. SIGecom: <https://sigecom.org/>. Last edition: <https://ec26.sigecom.org/>.
- Deadlines: not yet announced. Estimate from EC'26: abstract Monday 2 February 2026 and paper Monday 9 February 2026, both 11:59pm AoE ([EC'26 call for papers](https://ec26.sigecom.org/call-for-contributions-acm/papers/)). EC'26 final decisions came on 18 May 2026 and the conference ran 6-10 July 2026 in Rome.
- Page limit (EC'26): body up to 18 pages excluding title page and bibliography, single column, 10-point font, EC style files required. Appendices are allowed for review. Papers that skip the style files or exceed the limit "may be rejected without review".
- Review (EC'26): double-blind, two rounds, author response in the second round. Authors do not pick a track.
- arXiv (EC'26): allowed if the submission itself is anonymized. Simultaneous journal submission is allowed as long as the journal has not requested a revision. No concurrent submission to another archival conference.
- Fit: best match for the research question, the page budget, and the economics-heavy reference list.
- Acceptance rate: not stated on the official pages. A Northwestern news item reports 290 accepted of 1,115 submissions for EC'26 (about 26 percent). Unofficial.

### 2. KDD 2027 Research Track, Cycle 2 (ACM SIGKDD Conference on Knowledge Discovery and Data Mining)

- Official URL: <https://kdd2027.kdd.org/>. Conference 1-5 August 2027, San Jose.
- Deadlines: Cycle 1 closed (abstract 19 July 2026, paper 26 July 2026, AoE). For Cycle 2 the [research track call](https://kdd2027.kdd.org/research-track-call-for-papers/) only mentions "the February 2027 deadline". Exact days not yet announced. Estimate from KDD 2026 Cycle 2: abstract 1 February 2026, paper 8 February 2026, AoE ([KDD 2026 research call](https://kdd2026.kdd.org/research-track-call-for-papers/)).
- Page limit: 8 content pages, then references and an appendix with no page limit at submission. Camera-ready is 12 pages total with 9 of content.
- Review: double-blind, at least three reviews plus an area chair. A "Resubmit" decision can carry a paper into the next cycle.
- arXiv: "Authors may submit anonymized work that is already available as a preprint (e.g., on arXiv or SSRN) without citing it."
- Template: `\documentclass[sigconf,anonymous,review]{acmart}`.
- Fit: scale (1M markets), careful out-of-time evaluation, and benchmarks against many baselines suit KDD. Reviewers will press on method novelty.
- Other tracks: the [Applied Data Science track](https://kdd2027.kdd.org/applied-data-science-ads-track-call-for-papers/) asks for "deployed applications" and is single-blind. A research backtest is a weak fit there. The [Datasets and Benchmarks track](https://kdd2027.kdd.org/datasets-and-benchmarks-track-call-for-papers/) (single-blind, same page limits) fits only if the released dataset and benchmark become the headline.
- Acceptance rate: not stated on the official pages. Third-party reports put KDD 2026 research acceptance near 18 to 21 percent. Unofficial.

### 3. ICML 2027 (International Conference on Machine Learning)

- Official URL: <https://icml.cc/>. The 2027 pages return 404 today. The [future meetings page](https://icml.cc/Conferences/FutureMeetings) lists 2027 as "South America" with no dates.
- Deadlines: not yet announced. Estimate from ICML 2026: abstract 23 January 2026 AoE, paper 28 January 2026 AoE, notification 30 April 2026 ([ICML 2026 call](https://icml.cc/Conferences/2026/CallForPapers), [ICML 2026 dates](https://icml.cc/Conferences/2026/Dates)).
- Page limit (2026): 8 pages of main text, unlimited references, impact statement, and appendix. One extra page at camera-ready.
- Review (2026): double-blind.
- arXiv (2026): allowed. The preprint must not be advertised as an ICML submission during review.
- Fit: the calibration and LLM-forecaster parts fit. The finance backtests and microstructure links will read as application work, and ICML reviewers tend to discount that without a new method.
- Acceptance rate: not on the official pages I read. A third-party report gives 6,352 accepted of 23,918 for ICML 2026 (26.6 percent). Unofficial.

### 4. IJCAI 2027 (International Joint Conference on Artificial Intelligence)

- Official URL: <https://2027.ijcai.org/>. Kyoto, 7-13 August 2027, with a satellite event in Hengqin, 15-17 August 2027.
- Deadlines: abstract 4 January 2027, full paper 11 January 2027, both 23:59 AoE, notification 21 April 2027 ([IJCAI 2027 home page](https://2027.ijcai.org/)).
- Page limit: the 2027 call is not out. IJCAI-ECAI 2026 allowed 7 pages of body plus 2 pages of references ([2026 main track call](https://2026.ijcai.org/ijcai-ecai-2026-call-for-papers-main-track/)). Treat as an estimate.
- Review (2026): anonymized, two phases, summary reject after phase 1 for weak papers.
- arXiv (2026): non-anonymous preprints "will not result in rejection".
- Fit: broad AI venue with a history of AI-and-finance papers. Seven pages is very tight for this paper, and the deadline is the earliest of the realistic options.
- Acceptance rate: not stated in the call.

### 5. TheWebConf 2027 (ACM Web Conference, formerly WWW)

- Official URL: <https://www2027.thewebconf.org/>. Dublin, 10-14 May 2027.
- Deadlines: abstract 18 October 2026, full paper 25 October 2026, end of day AoE. Notification 4 January 2027 ([research track call](https://www2027.thewebconf.org/?p=296)).
- Page limit: 8 pages of main paper, with references and optional appendix up to 12 pages total. Short papers: 4 pages including references.
- Review: double-blind.
- arXiv: "Authors may submit anonymized work that is already available as a preprint (e.g., on arXiv or SSRN) without citing it."
- Template: acmart `sigconf, anonymous, review`.
- Fit: the "Web Economics and Digital Society" track covers online markets, and Polymarket is a web and blockchain platform. The fit is good. The deadline is 23 days away, which rules it out unless a near-complete draft already exists.
- Acceptance rate: not stated on the call. A third-party report gives 676 of 3,370 for the 2026 research track (20 percent). Unofficial.

### 6. UAI 2027 (Conference on Uncertainty in Artificial Intelligence)

- Official URL: <https://www.auai.org/>. The `uai2027` page returns 404 today.
- Deadlines: not yet announced. Estimate from UAI 2026: paper 25 February 2026, 23:59 AoE, notification 1 June 2026 ([UAI 2026 call](https://auai.org/uai2026/call_for_papers)).
- Page limit (2026): 8 pages plus unlimited references and appendices ([UAI 2026 submission instructions](https://www.auai.org/uai2026/submission_instructions)).
- Review (2026): double-blind.
- arXiv (2026): arXiv postings "are not considered dual submissions".
- Fit: calibration and probabilistic forecasting are core UAI topics. The trading and microstructure material would need to move to the appendix. A reasonable second try if EC or KDD is skipped, since the date falls two to three weeks later.
- Acceptance rate: not stated on the pages I read.

### 7. NeurIPS 2027

- Official URL: <https://neurips.cc/>. No 2027 dates posted.
- Deadlines: not yet announced. Estimate from NeurIPS 2026: abstract 4 May 2026, full paper 6 May 2026, AoE ([NeurIPS 2026 dates](https://neurips.cc/Conferences/2026/Dates)). If 2027 repeats this, the deadline falls inside the window.
- Page limit, review model, preprint policy: not checked for 2027.
- Fit: same concerns as ICML for the main track. The datasets and benchmarks track would suit a released Polymarket dataset with a forecasting benchmark. It also works as a resubmission target after an ICML or EC decision.

### 8. ICLR 2027 workshops

- Official URL: <https://iclr.cc/Conferences/2027/CallForWorkshops>.
- Deadlines: the accepted workshop list comes out on 29 November 2026. The suggested deadline for workshop contributions is 1 February 2027, and paper notifications are mandatory by 26 February 2027, 11:59pm AoE ([call for workshops](https://iclr.cc/Conferences/2027/CallForWorkshops)). Each workshop sets its own date and format.
- The page gives the workshop days as "April 29 and 30, 2026" in San Francisco. The year looks like a typo for 2027. Not confirmed.
- The ICLR 2027 main conference is closed: abstract 18 September 2026, paper 25 September 2026 AoE ([call for papers](https://iclr.cc/Conferences/2027/CallForPapers)).
- Fit: a forecasting, agents, or finance workshop would be a good low-stakes place for a 4-page version. Most ICLR workshops are non-archival, so a workshop paper usually does not block EC or KDD. Check each workshop's policy after 29 November. A 1 February workshop deadline collides with the EC and KDD deadlines.

### 9. ICAIF'26 workshops (Milan, 14-15 November 2026)

- Official URL: <https://icaif2026.org/workshop/>.
- Deadline: workshop paper submission extended to 12 October 2026, 23:59 AoE, notification 16 October 2026 ([important dates](https://icaif2026.org/important-dates/)).
- Relevant workshops listed there: "AI-Driven Market Microstructure in Centralized and Decentralized Finance" (<https://icaif-ai-driven.github.io/>) and "The 3rd Workshop on LLMs and Generative AI for Finance" (<https://ai4f.org>). I did not open the individual workshop sites, so page limits and archival status are unverified. A search result listed 7 October for the LLM workshop, which conflicts with the ICAIF page. Check the workshop site.
- Fit: on topic, but ten days is too short for a project at the literature-notes stage.

### 10. ICAIF 2027 (outside the window, listed as the fallback)

- Official URL: <https://icaif2026.org/> for the 2026 edition. No 2027 page or announcement found.
- ICAIF'26 timing: paper deadline 2 August 2026, extended to 9 August 2026, 23:59 AoE. Notification 1 October 2026. Conference 14-17 November 2026 in Milan ([important dates](https://icaif2026.org/important-dates/)). The 2026 edition is closed.
- Deadline for 2027: not yet announced. Estimate: early August 2027.
- Page limit (2026): 8 pages total in two-column `sigconf`, including figures and references ([call for papers](https://icaif2026.org/call-for-papers/)).
- Review (2026): double-blind, no rebuttal.
- arXiv (2026): prior technical reports and arXiv versions are allowed. Do not cite them in the submission.
- Fit: the closest community for ML plus empirical finance plus microstructure, and the most forgiving on method novelty.

## Checked and closed

- **AISTATS 2027**: abstract deadline 29 September 2026 has passed, paper due 6 October 2026, 23:59 AoE. No author changes after the abstract deadline. 8 pages, double-blind ([call for papers](https://virtual.aistats.org/Conferences/2027/CallForPapers)).
- **AAMAS 2027**: author registration on OpenReview was due 17 September 2026, abstract 1 October 2026, paper 8 October 2026, all AoE. 8 pages plus references, double-blind, arXiv allowed ([main track call](https://warwick.ac.uk/fac/sci/dcs/aamas2027/calls/call-for-main-track/), [instructions](https://warwick.ac.uk/fac/sci/dcs/aamas2027/calls/instructions/)). The registration step has passed.
- **KDD 2027 Cycle 1**: closed 26 July 2026.
- **ICAIF'26 main track**: closed 9 August 2026.
- **Financial Cryptography 2027**: submission 17 September 2026, firm deadline 24 September 2026, AoE ([call for papers](https://fc27.ifca.ai/cfp.html)). Closed.
- **ACM AFT 2027** (Advances in Financial Technologies): no 2027 call found. AFT 2026 had abstract registration on 20 May 2026 and papers on 27 May 2026 AoE per a search result for the [AFT 2026 call](https://aft.ifca.ai/aft26/CFP.html). I did not open that page. If repeated, AFT 2027 falls inside the window and suits the blockchain market-structure angle.
- **ICML 2027 workshops**: not announced. ICML 2026 suggested 24 April 2026 AoE for workshop contributions ([ICML 2026 call for workshops](https://icml.cc/Conferences/2026/CallForWorkshops)). Estimate for 2027: late April.

## Journal route

Short answer: send it to a conference first, post a preprint at the same time, and decide on a journal after the first round of reviews.

- A conference decision arrives in about three months. Finance and forecasting journals often take a year or more per round. For an MS student who wants a result on the CV, the conference cycle is the better first step.
- The Polymarket literature is moving quickly. The literature notes list several 2025-2026 working papers on the same data. Posting to arXiv and SSRN on submission day establishes priority. EC, KDD, ICML, IJCAI, UAI, TheWebConf, and ICAIF all allow this under their latest rules.
- EC keeps the journal path open (one-page abstract option, simultaneous journal submission). A full ICML or KDD proceedings paper makes a later journal version harder, because most journals want substantial new material beyond the proceedings version.
- Candidate journals if the conference route fails or as a follow-up:
  - *Transactions on Machine Learning Research*: rolling submission, double-blind on OpenReview, judged on technical correctness more than significance ([TMLR](https://jmlr.org/tmlr/)). A sound choice if the paper is solid but conference reviewers call it incremental.
  - *International Journal of Forecasting* (Elsevier): cited twice in `refs.bib`, and calibration plus forecast comparison is its core scope. The author guide returned HTTP 403, so length and review rules are unverified.
  - *Quantitative Finance* (Taylor and Francis): the author instructions returned HTTP 403. Unverified.
  - *The Journal of Financial Data Science* (<https://www.pm-research.com/content/iijjfds>): the site redirected to a login page. Unverified. It is practitioner-oriented, which suits the cost-aware backtests.
- A journal-first route makes sense in one case: an advisor in finance or economics wants a full-length working paper aimed at a field journal. Then SSRN first and EC with the one-page abstract option is the compatible conference.

## Acceptance rates

None of the official pages I read states an acceptance rate. The figures quoted above come from third-party pages found by search and are labeled unofficial. Do not cite them.

## Template on disk

- Location: `paper/template/ec26-submission-style-files/`. The zip is next to it at `paper/template/ec26-submission-style-files.zip` (966,295 bytes, SHA-256 `2f9e2264b66e36bb460bc4756a216f8d294c5c87a39fc3ad588093d6b91639c6`).
- Source: <https://ec26.sigecom.org/wp-content/uploads/2026/01/ec26-submission-style-files.zip>, linked from the [EC'26 call for papers](https://ec26.sigecom.org/call-for-contributions-acm/papers/). This is the EC'26 kit. The EC'27 kit does not exist yet. EC has updated the same files each year (the style file header lists yearly edits since 2017), so the 2027 kit should be a drop-in replacement.
- Start from `sample-ec-submission.tex`. It uses `\documentclass[format=acmsmall, review=false]{acmart}` with `\usepackage{acm-ec-26}`.
- Style file: `acm-ec-26.sty`, on top of the bundled `acmart.cls`. Bibliography style: `ACM-Reference-Format.bst`.
- The footer prints "Manuscript submitted for review to the 27th ACM Conference on Economics & Computation (EC'26)". Swap in the EC'27 style file when it is released, expected around January 2027.
- Author field for submission is anonymous (`\author{Submission 42}` in the sample). Title page holds title and abstract only. Body limit is 18 pages.
- Other files in the kit: `acmguide.pdf`, `sample-ec-submission.pdf`, `sample-bibliography.bib`, `mouse.eps`, `mouse.pdf`.
- For the KDD backup, the format is stock `acmart` with `sigconf,anonymous,review`. The `acmart.cls` in this kit is a copy bundled by EC. Get a current `acmart` from ACM or TeX Live before a KDD submission.

## Not verified

- EC 2027, ICML 2027, UAI 2027, NeurIPS 2027, ICAIF 2027, AFT 2027: no official dates exist yet. All dates shown for them are last year's.
- KDD 2027 Cycle 2: month only.
- IJCAI 2027 page limit and policies: 2026 values shown, 2027 call not released.
- Acceptance rates: no official source.
- Journal guidelines for IJF, Quantitative Finance, and JFDS: pages blocked.
- TheWebConf 2027 track description for "Web Economics and Digital Society": the track name is on the call, the topic list was not retrieved.
- ICAIF'26 individual workshop sites: not opened.
