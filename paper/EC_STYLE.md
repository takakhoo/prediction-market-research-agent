# How EC papers are written: a guide for the Polymarket mispricing paper

Compiled 2026-10-02 from the EC'26 call for papers, the EC'26 LaTeX style files, the EC'22 to EC'26 accepted-paper lists, award pages, one SIGecom Exchanges program-chair note, and the full text of six accepted empirical papers. Every rule in Section 1 links to the page it was read on. Every structural claim in Section 2 comes from reading the paper itself, with page numbers where they matter. Things I could not verify are flagged inline and collected at the end.

## 1. Formal rules (EC'26 call for papers; EC'27 not yet published)

Status of EC'27: `ec27.sigecom.org` does not resolve as of today, and neither `sigecom.org/events.html` nor the EC'26 site mentions EC'27. Plan against the EC'26 rules below and check `ec27.sigecom.org` in late 2026. The EC'25 and EC'24 CFPs have the same page limit, format and appendix language, so these rules have been stable for at least three cycles.

Source for everything in this subsection unless noted: https://ec26.sigecom.org/call-for-contributions-acm/papers/

Page limit. "The body of the submission (excluding the title page and the bibliography) may be up to 18 pages long." Figures and tables sit inside the body, so they count. The CFP has no separate figure or table allowance.

Title page. "The title page should only contain the title, submission number, and the abstract and it can also include a table of contents." The sample file in the style zip puts `\maketitle` and an optional `\tableofcontents` inside a `titlepage` environment, then starts Section 1 on the next page.

Column format and font. Single column, 10-point. The style zip (https://ec26.sigecom.org/wp-content/uploads/2026/01/ec26-submission-style-files.zip) contains `acmart.cls`, `acm-ec-26.sty`, `ACM-Reference-Format.bst` and `sample-ec-submission.tex`. The sample loads `\documentclass[format=acmsmall, review=false]{acmart}` and `\usepackage{acm-ec-26}`; `acmart.cls` sets `acmsmall` to 10pt. The `.sty` removes the ACM copyright block, prints "Manuscript submitted for review to the 27th ACM Conference on Economics & Computation (EC'26)" in the footer of the title page, and puts short authors and page number in the running head. The sample file recommends `\setcitestyle{authoryear}` ("we recommend using the author-year citation style") and loads `booktabs`. Papers that do not use the style files "may be rejected without review." No Word template is offered.

Anonymization. "The review process is double blind." Authors must make sure "their identity is not easily revealed from the submission itself." The CFP's own example: refer to prior work as "XYZ et al. showed," never "we showed." The sample `.tex` sets `\author{Submission 42}` and tells you not to include acknowledgements. Posting to arXiv is allowed (see below), so anonymization concerns the submitted PDF only; the paper may already exist online under your name.

Appendices. "An appendix of unrestricted length may be included for review purposes only" (EC'24 wording: "an appendix of arbitrary length may be included at the end of the paper only for the review process"). It "will not appear in published versions" and "reviewers read appendices at their discretion." Practical consequence: nothing load-bearing goes only in the appendix. Robustness tables, extra specifications, data-cleaning details and proofs can live there, but the main claim and the evidence for it must fit in 18 pages.

Code and data. "Authors are strongly encouraged to submit their code and data, if any. Such material should be archived as a single zip file and submitted as supplementary material."

arXiv and prior presentation. "It is acceptable to submit work that has been presented in public (provided there are no published proceedings) or has been uploaded to arXiv or similar online archives, provided the submission itself is anonymized."

Journal and dual submission. Simultaneous submission to a journal is allowed only if the paper "has not been accepted" and "has not received a request for a revision" (revise-and-resubmit, major or minor). A paper with a revision request is ineligible for the main track but may be nominated for "Highlights Beyond EC." Papers under review at another archival conference are not eligible.

One-page abstract option. "Authors of accepted papers can ask that only a one-page abstract of the paper appear in the proceedings, along with a URL pointing to the full paper." You must guarantee the link works for at least two years. This exists so that a later journal version is not blocked by a prior proceedings publication. The EC'13 program-chair note (https://sigecom.hosting.acm.org/exchanges/volume_12/1/MCAFEE.pdf, p. 6) adds one thing the current CFP does not say: the SIGecom executive committee "decided that only full length paper qualify" for best-paper awards. Treat that as historical unless the EC'27 CFP says otherwise.

Forward-to-journal. Accepted papers may forward their reviews to partner journals. Relevant partners for this paper: Management Science, Operations Research, Marketing Science, Quantitative Marketing and Economics, Games and Economic Behavior, Journal of Political Economy, Review of Economic Studies, ACM TEAC.

Tracks. This changed in 2026. EC'24 and EC'25 had four author-selected tracks (Theory, Applied Modeling, Empirics, AI). EC'26 says "papers will be matched to one of thirteen Track Chairs via the same matching algorithm assigning PCs and SPCs, and authors will not select their Track." You pick topic areas instead; the relevant ones for this paper are "Crowdsourcing and information elicitation," "Econometrics," "Economic aspects of neural networks and large language models," "Blockchain and cryptocurrencies," and "Online platforms and applications." The old Empirics track definition is still the best statement of what reviewers expect from an empirical submission (EC'24 CFP, https://ec24.sigecom.org/call-for-contributions-acm/papers/): "Typical papers in this track draw significant insights from real or synthetic data, through access to new data sources or experiments, or through novel analysis of existing data sources or experiments."

Evaluation criteria (EC'25 CFP, https://ec25.sigecom.org/call-for-contributions-acm/papers/): "significance of the contribution, originality, relation to prior research, technical quality, and exposition." The EC'26 page has no per-track or per-method criteria.

Review rounds and author response. Each paper gets one Track Chair, a primary and a secondary SPC member, and at least two first-round PC reviews. "Authors will be notified by March 26 whether the paper advances to the second round." Papers that advance get at least one more review. Second-round reviews are sent April 21 and the author response window is April 21 to April 25. The response should address concrete "Questions for Authors" and correct factual errors; the CFP says challenging subjective assessments or promising edits is inappropriate. Final decisions May 18. EC'26 dates: abstract Feb 2, full paper Feb 9, conference July 6-10 in Rome. Expect EC'27 dates to be a week or so either side of these.

LLM use. Allowed if the work is the authors' own intellectual contribution and the authors take responsibility for accuracy. Disclosure scales with use: spelling and grammar need no disclosure; "if entire paragraphs/tables/images/graphs/etc. are generated, authors should prepare an appendix or supplemental materials describing the tool used (including its version), the prompts provided as input, and any post-generation edits." For this paper, that means the LLM-forecaster prompts belong in an appendix anyway, and any LLM-drafted prose needs a disclosure note.

Open access and attendance. ACM is fully open access from 2026-01-01; APCs apply unless your institution participates or you get a waiver; extended abstracts carry no APC. At least one author must register and present in person.

## 2. How strong empirical EC papers are built

Six accepted papers, read in full or in large part. Four are on data-driven platforms or markets, two are on forecasting and crowds, and two involve LLMs. Where an EC version was not retrievable I read the public working-paper or journal version and say so.

### 2.1 Atanasov, Witkowski, Mellers, Tetlock. "Crowd Prediction Systems: Markets, Polls, and Elite Forecasters." EC'22; International Journal of Forecasting 41(2), 2025.

Version read: SSRN 4691513 preprint dated April 10, 2024, 51 pages, https://faculty.wharton.upenn.edu/wp-content/uploads/2016/11/Crowd-Prediction-Systems.pdf. Listed on the EC'22 accepted-papers page (https://ec22.sigecom.org/program/accepted-papers/).

Closest match to your paper in subject. Prediction markets (CDA and LMSR), Brier scores, elite versus sub-elite crowds, four seasons of the IARPA ACE tournament.

Introduction: 11 pages in the preprint (pp. 2-12), unusually long because it absorbs the literature review as subsections 1.1 "Crowd Prediction Systems," 1.2 "Large Crowds versus Small, Select Crowds," and 1.3 "Research Questions." The first paragraph states why crowd prediction matters (settings with little historical data). The second paragraph frames the "central practical question" from a manager's point of view. The third opens "Our main research contribution lies in quantifying the impact of prediction system architecture and individual forecaster track record on aggregate performance" and then says explicitly what is new ("We are the first to compare the aggregate performance of small, elite forecaster crowds across two prediction systems"). Section 1.3 states one main and two complementary research questions in italics, each followed by the authors' ex ante expectation. Hypotheses are stated before results and the paper later reports when results contradicted them ("This finding is inconsistent with our expectations," p. 40).

Section list: 1 Introduction (1.1, 1.2, 1.3), 2 Methods (2.1 Crowd Prediction Systems with the LMSR price formula as Equation 1 and the extremization formula as Equation 2; 2.2 Participants; design tables), 3 Results (3.1 main question, 3.2 complementary question 1, 3.3 complementary question 2), 4 Discussion (4.1 Research Implications, 4.2 Practical Implications, 4.3 Limitations and Future Directions, 4.4 Conclusion), Acknowledgement, References.

Results reporting: tables dominate. Design tables (Tables 1-4) show the season-by-condition grid and n per cell before any result. Result tables report n, correlation r and p-values (Table 11) or OLS coefficients with standard errors in parentheses and star notation (Table 12, "* p < .05, ** p < .01"). In-text statistics are given in parentheses: "(b = -.034, p < .001)," "(z = 3.71, p < .001)." Mixed-effects models and sub-sampling simulations serve as sensitivity analyses and are named as such ("Sensitivity analyses with the alternative performance measures yielded similar results. See Table 12, Columns B and C").

Limitations: a named subsection, 4.3, placed after the practical implications and before the conclusion. It opens "As is true for virtually all empirical investigations ... the current results should be generalized with caution," then lists specific threats (question domain, non-random assignment of elite forecasters) and quantifies how large a swing would be needed to overturn the main null ("a large swing, equivalent to a 25% change in relative Brier scores, would have been needed").

Tone: first person plural throughout. Hedged where the design is weak ("may have provided a small benefit," "it is plausible that limiting the number of traders may adversely impact activity") and direct where the test is clean ("This study is the first to demonstrate that small, elite crowds outperform large, less selective crowds"). Economic framing is explicit: results are tied to Hanson's thin-market motivation for LMSR and to the efficient-market and marginal-trader hypotheses (pp. 5-6).

### 2.2 Atanasov, Karger, Tetlock. "Full Accuracy Scoring Accelerates the Discovery of Skilled Forecasters." EC'24.

DOI https://doi.org/10.1145/3670865.3673583. Listed on https://ec24.sigecom.org/program/accepted-papers/. I could not retrieve the full text (ACM DL and ResearchGate both returned 403), so only the abstract is verified: the paper proposes a Full Accuracy Score that combines proper ground-truth scores with proxy scores measuring distance from consensus, and shows it predicts final forecaster performance better than ground-truth scoring alone and identifies skilled forecasters sooner. Relevant to you because it is a scoring-rule paper with an empirical test, accepted at EC, from the same group as 2.1. Treat its structure as unverified.

### 2.3 Horton, Filippas, Manning. "Large Language Models as Simulated Economic Agents: What Can We Learn from Homo Silicus?" EC'24.

Version read: arXiv 2301.07543v2 (February 2026), https://arxiv.org/pdf/2301.07543. Listed on the EC'24 accepted-papers page.

The LLM paper EC reviewers will have in mind when they read your LLM-forecaster section.

Introduction: 5 pages (pp. 2-6). No separate related-work section; prior work is cited inline and the growing LLM-agent literature is summarized in one paragraph near the end of the intro. The contribution is stated in one paragraph: "the contributions of this paper are now twofold. First ... Second, the relative ... contribution of this paper is drawing the connection to the common research paradigm of economics." Note the final sentence of that paragraph, which is the kind of economic positioning EC wants: "LLM experimentation is more akin to the practice of economic theory, despite superficially looking like empirical research." A one-paragraph roadmap follows.

Section list: 1 Introduction, 2 Experiments (2.1 to 2.5, one per recapitulated experiment, each with a subsection on generalizability or calibration), 3 Why and when we can learn from Homo silicus, 4 conceptual critiques, 5 Conclusion, Appendices A (additional figures and tables), B (primer on LLMs), C (figures from the original draft).

Results reporting: the body uses figures throughout and pushes tables to the appendix. Every figure has a long italic "Notes:" block under it giving the model, temperature, number of samples, the confidence-interval method ("Error bars represent 95% multinomial Wilson confidence intervals") and a URL to the notebook that generated it. Regression coefficients are shown as dot-and-whisker plots (Figure 2) with the full specification pushed to an appendix table (A2). Robustness is built into the experiment design: translated, alternative-phrasing and adversarial-phrasing permutations, then "At a high level, the original pattern appears quite robust." Model heterogeneity is reported by name (GPT-4o, Claude-Sonnet-3.5, Llama-3-70B, DeepSeek) and the authors say outright when models disagree.

Limitations: no named section. Instead, a candid paragraph in the intro about model deprecation ("Results from these now woefully out-of-date models appear in Appendix A ... even our updated experiments will become dated") and a full section (4) on conceptual critiques including memorization.

Tone: first person plural. Direct and informal for an economics paper ("Interestingly, without any endowment, some models choose efficiently while others tend to be selfish"). Code, prompts and data are linked from every figure.

### 2.4 Almog, Gauriot, Page, Martin. "AI Oversight and Human Mistakes: Evidence from Centre Court." EC'24.

Version read: arXiv 2401.16754v3 (February 2025), titled "Human Responses to AI Oversight: Evidence from Centre Court," 34 pages plus appendix, https://arxiv.org/pdf/2401.16754. Listed on the EC'24 accepted-papers page.

A clean example of an EC empirical paper that pairs reduced-form evidence with a structural model.

Introduction: about 3 pages (pp. 2-4) before a 3-page subsection 1.1 "Related Literature." The intro follows a strict template: motivation (two forces: ML prediction quality and cheap monitoring), a concrete example (Zalando), the gap ("very little is known about how humans respond when their decisions might be overruled by AI"), the claim ("To the best of our knowledge, we provide the first field evidence that AI oversight can influence human decision-making"), why the setting is good for identification (one paragraph listing four advantages), headline numbers in the intro itself ("umpires lowered their overall mistake rate by 8% (1.1 p.p.) ... the mistake rate actually increased by 34% (8.5 p.p.)"), the economic mechanism (asymmetric psychological costs of Type I and Type II errors), the structural estimate (37%), then a roadmap paragraph.

Related literature: early, as 1.1, organized by literature (AI-assisted decisions, social image, monitoring, rational inattention), each paragraph ending with a sentence on what this paper adds.

Section list: 1 Introduction (1.1 Related Literature), 2 Setting and Data (2.1 institutional background, 2.2 data sets including 2.2.3 Video Auditing of the merge), 3 Empirical Results (3.1 overall mistake rate, 3.2 shift in Type I and Type II errors), 4 Recovering the AI Oversight Penalty (model and structural estimation), 5 heterogeneity, 6 discussion, appendices A (data construction and merge algorithm) and B (additional figures).

Results reporting: one regression table in the body (Table 2) with four columns adding controls, standard errors in parentheses, stars at 10/5/1 percent, N and baseline mean in the footer. The equation is numbered and every symbol defined in the following paragraph. Heterogeneity by distance bin is a coefficient plot with 95% CIs (Figure 2), an event-study split by period (Figure 3), and a time-trend plot (Figure 4). Robustness to "contamination bias" is a one-treatment-at-a-time re-estimation referenced to an appendix figure (B.2). Data validity gets its own subsection: they hand-audited 43 matches of video to measure the merge error rate (99.3% merge, 4.9% mis-merged).

Limitations: no named section. Threats are addressed at the point they arise, usually in footnotes (umpire pool stability, footnote 22; the "before/after" shorthand, footnote 11) or inline ("It is an open question as to whether humans respond differently to human and AI monitoring, thus we cannot assume ...").

Tone: first person plural, moderately hedged ("Our reduced-form estimates suggest," "may reflect their growing adaptation"). Effect sizes always given both in percent and percentage points.

### 2.5 Fu, Jin, Liu. "Does a Human-algorithm Feedback Loop Lead To Error Propagation? Evidence from Zillow's Zestimate." EC'25.

Version read: NBER Working Paper 29880 (March 2022), earlier title "Human-Algorithm Interactions: Evidence from Zillow.com," https://www.nber.org/system/files/working_papers/w29880/revisions/w29880.rev0.pdf. Listed on https://ec25.sigecom.org/program/accepted-papers/. The EC version likely differs; structure below is from the NBER version.

Introduction: 3.5 pages. Opens with the broad concern (black-box algorithms), narrows to the implicit one-directional assumption, then "We use Zillow's Zestimate algorithm as an example." Headline estimates appear in the intro with the identification strategy named ("the IV results suggest that listing price would go up 0.66% for every 1% increase in the house's pre-listing Zestimate"). Contributions are a numbered paragraph: "This paper makes several contributions. First, to our knowledge, we are among the first to provide explicit evidence on ... Second, we identify the potential positive and negative implications ..." Roadmap paragraph follows.

Related literature: a separate Section 2 "Literature Review," three pages, immediately after the intro.

Section list: 1 Introduction, 2 Literature Review, 3 Context and Data (3.1 Background with screenshots of the platform, 3.2 Data with Table 1 summary statistics and a numbered list of sample filters with the count dropped at each step), 4 Characterization of Zestimate's Role (sequence-of-events figure, then 4.1 seller response with Equation 1 and IV, 4.2 Zestimate update after listing, buyer response, RDD), 5 implications, 6 limiting forces, 7 conclusion, appendix tables A1-A4 for OLS versus IV and alternative instruments.

Results reporting: regression tables with standard errors in parentheses and stars, one column per subsample (All, Austin, Boston, Pittsburgh, Houses, Condos), Observations, R-squared and fixed-effects rows in the footer. Event-time figures with 95% CIs. The instrument's exclusion restriction gets two full paragraphs of argument plus two alternative instrument definitions as robustness, all cross-referenced to appendix tables.

Data description: large. Section 3 is about 5 pages including screenshots and a filter-by-filter sample construction ("This removes 3,445 properties from the sample"). Reviewers of platform-data papers expect this.

Tone: first person plural. The intro states both possible interpretations of the feedback loop (transparency versus disturbance propagation) before reporting which one the data support.

### 2.6 Hollenbeck, Larsen, Proserpio. "The Financial Consequences of Legalized Sports Gambling." EC'25; Management Science (2025).

Version read: working paper dated October 2024, 18 pages of body plus references and appendix, https://assets.senate.mn/committees/2025-2026/1007_Committee_on_Finance/The-Financial-Consequences-of-Legalized-Sports-Betting.pdf (also SSRN 4903302). Listed on the EC'25 accepted-papers page.

The most compact of the six and the closest to the 18-page EC body limit. Useful as a template for how little space the setup can take.

Introduction: 3 pages, with the literature woven in as the last three paragraphs rather than in a separate section. Structure: policy context with numbers, who is harmed, "This paper studies the causal impact of ...", data in one sentence ("roughly 7 million U.S. adults"), outcomes listed, empirical strategy in one paragraph with both treatment definitions, then the relation to two concurrent papers with an explicit statement of what this paper adds ("Our work complements theirs by extending ...").

Section list: 1 Introduction, 2 Background and Data (2.1 legal background, 2.2 data, 2.3 treatment definitions, 2.4 outcomes with a bold run-in heading per outcome and Table 1 pre-treatment summary statistics), 3 Empirical Strategy (one page: estimator choice with citations to Callaway and Sant'Anna and Borusyak et al., the identifying assumption, and a pointer to Appendix B for identification checks), 4 Aggregate Effects (4.1 to 4.4), 5 Discussion, References, Appendix A onward.

Results reporting: event-study figures with 95% CIs for every outcome (Figures 2-4), then one summary table of ATTs (Table 2) with standard errors in parentheses, stars, clustering stated in the note, and a Benjamini-Hochberg correction for multiple outcomes stated in the text. Effects are translated into economic magnitudes in the Discussion ("roughly 30,000 additional annual bankruptcies and an additional $8 billion in annual collections"). Heterogeneity by gender, age and income is in Appendix C.

Limitations: no named section. One paragraph in the Discussion: "It is important to remember that we measure average effects for the full population ... We do not know from our data the proportion of this population that is negatively affected." Policy implications follow and are hedged ("our results suggest that policies meant to restrict or mitigate negative financial outcomes may be warranted").

Tone: first person plural, plain. Counterintuitive results are flagged and explained in place ("this is somewhat counterintuitive. However, in Section 4.3, we show that credit agencies appear to be lowering credit card limits").

### 2.7 Gao, Han, Liang. "How Well Do LLMs Predict Human Behavior? A Measure of their Pretrained Knowledge." EC'26.

Version read: arXiv 2601.12343v1 (January 2026), https://arxiv.org/pdf/2601.12343. Listed on https://ec26.sigecom.org/program/accepted-papers/.

Included because it is the most recent EC-accepted LLM evaluation paper and it shows how EC wants an evaluation metric motivated. The paper defines "equivalent sample size" (the amount of task-specific data a conventional model needs to match a fixed LLM), builds an inference procedure for it with new asymptotic theory for cross-validated error, and applies it to PSID outcomes. Introduction: 3 pages, then 1.1 "Related Literature" with bold run-in labels per strand. Section 2 "Framework" has numbered Examples and a formal Definition 2.1 before any data. The empirical application is one section near the end. The point for your paper: when you introduce a metric (walk-forward edge net of fees, calibration at fills), EC readers want it defined formally, interpreted in an economic unit, and separated from the estimation procedure.

### 2.8 Patterns across the six

Length of introduction: 3 to 5 pages in a single-column working-paper layout, so roughly 3 to 4 pages in the EC 10-point single-column format. Atanasov et al. run longer because their literature review lives inside the intro.

Contribution statement: always present, always explicit, usually one paragraph beginning "This paper makes several contributions" or "the contributions of this paper are twofold," placed after the headline results and before the roadmap. Headline numbers appear in the introduction in five of six papers.

Related work placement: three patterns, all accepted. (a) Subsection 1.1 inside the introduction (Almog et al., Gao et al.). (b) Separate Section 2 right after the intro (Fu et al.). (c) Woven into the intro with no heading (Hollenbeck et al., Horton et al.). Nobody puts related work at the end.

Data section: a full section with institutional background, a summary-statistics table, and a filter-by-filter account of sample construction. Fu et al. and Hollenbeck et al. spend 4 to 5 pages here. Almog et al. add a validation subsection measuring their own data-construction error rate.

Identification or methodology section: short and explicit. Hollenbeck et al. do it in one page: estimator, why that estimator, the identifying assumption, where the checks are.

Results: regression tables with standard errors in parentheses and 10/5/1 percent stars, N and baseline mean in the footer, one column per specification or subsample. Event-study and coefficient plots with 95% CIs for heterogeneity and dynamics. Every figure and table carries a notes block that names the CI method, clustering and sample. Multiple-testing corrections are stated when many outcomes are tested (Hollenbeck et al.). Effect sizes are given in both relative and absolute units and translated into economic magnitudes.

Robustness: named as such and placed either in a subsection at the end of the results or in appendix tables with a sentence in the body pointing to them. Common forms: alternative instrument or treatment definition, subsample splits, alternative estimator, alternative outcome measure, time-period splits.

Limitations: either a named subsection in the Discussion (Atanasov et al.) or a paragraph in the Discussion plus footnotes at the point each threat arises (the other four). None of them bury limitations in the conclusion.

Economic interpretation: every paper has one. Atanasov et al. tie to Hanson's thin-market argument and the marginal-trader hypothesis. Almog et al. build a rational-inattention model. Fu et al. frame transparency versus propagation. Hollenbeck et al. end with policy. Horton et al. argue LLM experiments belong to the theory tradition.

Tone: first person plural in all six. Hedging scales with the strength of identification: direct for clean tests, "suggest" and "may" for interpretive claims. No paper uses "state of the art," "novel framework" or similar.

Section lists converge on: Introduction (with contributions and roadmap); Related work (early, in one of the three positions above); Setting/Background and Data; Empirical strategy or Framework; Results (main, heterogeneity, robustness); Model or Mechanism (optional, present in Almog et al. and Gao et al.); Discussion (implications, limitations); Conclusion; References; Appendix.

## 3. What EC reviewers reward and penalize for empirical work

Direct evidence is thin. SIGecom Exchanges has published no program-chair notes since EC'13 that I could find (volumes 20 to 24 contain surveys and letters only, https://sigecom.hosting.acm.org/exchanges/), and the EC'26 site has no public reviewer-guideline page. What follows combines the one published chair note, the CFP language, the award record, and the structure of the accepted papers above.

From McAfee and Tardos, "Notes from the EC'13 Program Chairs" (https://sigecom.hosting.acm.org/exchanges/volume_12/1/MCAFEE.pdf):
- Reviewer disagreement is driven by what different disciplines find interesting: "An important source of unpredictability in evaluating papers is what the reviewers find interesting. This difference was especially acute when reviewers have very different backgrounds (some are economists, others are computer scientists)." Write for both readers. An economist SPC will ask what the economic question is; a CS reviewer will ask whether the method is sound and reproducible.
- Errors get caught and sink papers: "The review process identified a number of errors in manuscripts ... It would be desirable to reduce the number of errors in submissions. One way to achieve this is for authors to seek feedback from their colleagues before submission, and avoid the 'just in time' production process favored by many computer scientists."
- The discussion phase decides more than the initial scores do: "The discussions, involvement of the SPC, and author feedback had a major effect on the final decision."
- Author feedback was 500 words and worked when "the PC and SPC suspected that the paper had a mistake, or where the PC and SPC had questions for the author." The EC'26 process keeps this shape (response to "Questions for Authors," factual corrections only).
- The empirical track was the smallest in 2013 (50 submissions, 16 accepted, versus 167/52 for theory), with similar acceptance rates. By EC'24 the accepted list had grown to 343 papers across tracks and the empirical share had risen visibly, but the list is still dominated by theory.

From the CFP and track definitions:
- The Empirics track definition asks for "significant insights from real or synthetic data" through "new data sources" or "novel analysis of existing data sources." New data (Polymarket fills at scale) is itself a contribution if described carefully. "Novel analysis" means the method must be justified as well as applied.
- Evaluation criteria are generic ("significance, originality, relation to prior research, technical quality, exposition"). "Relation to prior research" is listed explicitly, which is why every accepted paper has an early related-work section that states what is added.
- Code and data are "strongly encouraged." Among the papers above, Horton et al. link a notebook from every figure and ship a Python package. Fu et al., Hollenbeck et al. and Almog et al. use proprietary or scraped data and compensate with very detailed construction descriptions.

From the award record:
- Exemplary Empirics track winners: EC'23 Lin and Strulov-Shlain, "Choice Architecture, Privacy Valuations, and Selection Bias" (https://ec23.sigecom.org/program/plenary-speakers/); EC'24 Bauer and Hnilo, "Scars of the Gestapo: Remembrance and Privacy Concerns" (https://ec24.sigecom.org/program/main-technical-program/index.html); EC'20 Ananthakrishnan, Proserpio and Sharma, "Does Quality Improve with Customer Voice? Evidence from the Hotel Industry" (https://sigecom.org/award-paper.html). EC'25 track award winners were not listed on any page I could reach. All three winners are causal-inference papers with a clearly stated economic question and a credible identification strategy. None is a pure measurement or benchmark paper.
- Best-paper winners from 2023 to 2025 were all theory (Deb and Renou; Cavallo and Dogan, applied modeling; Arunachaleswaran et al.). Do not expect a best-paper award for an audit; aim for the empirics track award.

What this implies, concretely:

Is an economic interpretation expected? Yes. Every accepted empirical paper above ties its findings to an economic mechanism or question (market microstructure, rational inattention, information transparency, consumer harm). A pure "we measured mispricing and here are the numbers" paper will be read by the economist SPC as descriptive. Your paper has a natural economic frame: digital-option pricing gives a no-arbitrage benchmark, mispricing at fills measures the limits of arbitrage net of transaction costs, and the walk-forward and LLM results speak to whether the mispricing is exploitable information or compensation for risk and frictions. Say which one you think it is and what evidence separates them.

Is theory required? No. Hollenbeck et al. and Fu et al. have no model. But Almog et al. and Gao et al. show that a short model or formal definition section raises the ceiling. A one-page section that writes down the pricing benchmark, the definition of mispricing at a fill, and the condition under which a trader captures it (fees, slippage, resolution risk) would read as "applied modeling" to the committee without pretending to be a theory paper.

How much space goes to data? About a quarter of the body. In an 18-page EC paper, expect 3 to 4 pages on the platform, the fill data, the pricing inputs, the sample filters with counts, and summary statistics. Reviewers of platform-data papers check this section hardest because they cannot see the data.

What gets penalized: results that depend on choices the paper does not defend (fee assumptions, which fills count, lookahead in walk-forward splits); missing standard errors or CIs; robustness only in an appendix with no body pointer; a related-work section that lists papers without saying what is added; claims in the abstract that the body hedges; and, per McAfee and Tardos, arithmetic or coding errors that a reviewer finds. For LLM components specifically, Horton et al. set the expectation that you report model names and versions, temperature, sample counts, and prompt text, and that you test prompt-wording robustness.

What gets rewarded: a new dataset described well enough to be trusted; a question an economist recognizes; identification or validation steps that preempt the obvious objection (Almog et al. hand-audited their merge; Fu et al. argued the exclusion restriction for two paragraphs and tried two alternative instruments); headline numbers in the introduction; magnitudes translated into dollars or basis points; and an honest limitations paragraph that quantifies how wrong the main result could be.

## 4. Checklist: making the draft read like an EC paper rather than an ML paper

1. Open the introduction with the economic question and the setting rather than the method. First paragraph: why mispricing in prediction markets matters and to whom. Second: what is new about the data (real fills at scale). Headline numbers by the end of page 2.
2. Write a contributions paragraph of the form "This paper makes three contributions. First ... Second ... Third ..." after the headline results and before a one-paragraph roadmap. No bullet list of contributions in the body (the EC sample file shows one, but none of the six accepted papers use it).
3. Put related work early, as Section 1.1 or Section 2, organized by literature (prediction-market efficiency: Wolfers and Zitzewitz, Page and Clemen, Cowgill and Zitzewitz; scoring and aggregation: Atanasov et al.; LLM forecasting and LLM agents: Horton et al., Gao et al.). End every paragraph with one sentence on what this paper adds to that strand.
4. Give data its own section with: platform mechanics (order book, fees, resolution), pricing inputs (underlying price feeds, volatility estimates), a numbered list of sample filters with the count removed at each step, and a summary-statistics table. Validate anything you constructed (fill matching, resolution labels) and report the error rate the way Almog et al. report their merge error.
5. State the pricing benchmark and the definition of "mispricing at a fill" formally, in a numbered equation with every symbol defined in the following sentence. Say what fees, slippage and resolution risk are netted out and why.
6. Make the empirical strategy section short and explicit: estimator, why that estimator, the identifying or no-lookahead assumption for walk-forward models, and where the checks are.
7. Report main results in regression-style tables: standard errors in parentheses, stars at 10/5/1 percent, N and a baseline mean in the footer, one column per specification or subsample, a notes block naming clustering and sample. Use coefficient plots or event-time plots with 95% CIs for heterogeneity across asset class, horizon, liquidity and time.
8. Translate every effect into two units: relative (percent) and absolute (basis points, dollars per contract, Brier points). Add a back-of-the-envelope aggregate (dollars of mispricing captured or left on the table per month) in the discussion.
9. Correct for multiple testing when you report many contracts, horizons or models, and say which correction (Hollenbeck et al. use Benjamini-Hochberg and state it in the table note).
10. Name the robustness section and put one sentence in the body for each check that lives in the appendix: alternative fee assumptions, alternative volatility estimators, excluding thin markets, alternative walk-forward windows, alternative LLM prompts and model versions.
11. For the LLM forecasters, follow Horton et al.: model name and version, temperature, number of samples per question, prompt text in an appendix, prompt-wording robustness, and a leakage discussion (training cutoff versus question resolution dates, as Gao et al. do with "static open-source models with documented training cutoffs"). Disclose any LLM use in writing the paper per the CFP.
12. Write a limitations paragraph in the discussion that names the main threats (sample period, platform-specific microstructure, survivorship in resolved contracts, unobserved trader identity) and, where possible, says how large an error would be needed to overturn the main result.
13. Give the economic interpretation a home: either a short model section before results or a mechanism subsection in the discussion that says whether the mispricing reflects limits to arbitrage, risk compensation, or information not yet in prices, and which of your results discriminates between them.
14. Keep the body at or under 18 pages in the EC style, with title page and references outside the count; move proofs, extra tables and prompts to an unrestricted appendix, and remember reviewers may not read it.
15. Use first person plural, author-year citations, `booktabs` tables, and the EC'26 style files unchanged. Anonymize: "Submission NNN" as author, no acknowledgements, no self-citations phrased as "our prior work." Submit code and data as a single zip.
16. Have a colleague check the arithmetic and the code paths that produce every number in the tables before submission. McAfee and Tardos single out errors as a cause of rejection, and the EC author response is limited to factual corrections and reviewer questions.

## 5. Not verified

- EC'27 dates, location, CFP and any rule changes. No EC'27 page exists yet.
- The full text and structure of Atanasov, Karger and Tetlock (EC'24); only the abstract was accessible.
- EC'25 exemplary track award winners; the EC'25 program page lists only the best paper.
- The EC-proceedings versions of Fu et al. and Hollenbeck et al.; I read the NBER working paper and the October 2024 working paper respectively, and the EC versions may be shorter or restructured.
- Any current written reviewer guidelines for EC. None are public. The reviewer-side claims in Section 3 are inferred from the CFP, the EC'13 chair note, and the accepted papers.
- Whether the "full-length papers only" rule for best-paper eligibility (EC'13 note) still holds.
