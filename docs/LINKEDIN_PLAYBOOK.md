# LinkedIn Launch Playbook — Agentic S&OP Copilot

## Thesis

Most supply chain pros on LinkedIn write *think pieces* about agentic AI. Almost nobody is shipping a working artifact and explaining the build. That's the gap. We exploit it with a 6-week build-in-public series, not a single launch post.

Why weekly cadence beats a single launch:
- LinkedIn's algorithm rewards repeated relevance — each post compounds the previous week's followers.
- A series gives recruiters and hiring managers multiple touchpoints to remember you.
- "Building" is more shareable than "built" — people root for journeys, not announcements.
- If a week's update flops, you've got next week. If you put everything into one post and it flops, you lose months of work.

## 6-Week Content Calendar

| Week | Post type      | Theme                                                  | Format            |
|------|----------------|--------------------------------------------------------|-------------------|
| 0    | Kickoff        | "I'm building an Agentic S&OP Copilot in public"       | Text + image      |
| 1    | Progress       | Data prep on M5 + lessons from working with 30K SKUs   | Carousel (6 slides) |
| 2    | Progress       | Forecast Agent — why agents shouldn't do arithmetic    | Carousel + GIF    |
| 3    | Progress       | Anomaly Agent — statistical rules + LLM ranking        | Video (90s demo)  |
| 4    | Progress       | Root-Cause Agent + the multi-agent orchestrator        | Carousel + diagram|
| 5    | **Launch**     | Live demo, public URL, what I learned                  | Video + carousel  |
| 6    | Retrospective  | "5 things I learned shipping an agentic AI in 6 weeks" | Carousel          |

After week 6, keep the flywheel going with one post every 1-2 weeks: a teardown of someone else's agentic system, a "v2 is shipping" post, a hiring market take, etc. Goal is to become *the* demand-planner-who-ships-agents in your network within 90 days.

## Post Anatomy (use for every post)

```
[HOOK]      1-2 short lines. Pattern: contrarian claim, surprising number, or
            "I spent X doing Y, here's what I learned."

[CONTEXT]   Who you are + what you're building. 1-2 lines. Skip if you've already
            built recognition in the series.

[MEAT]      The actual substance: what you did this week, with one concrete
            takeaway. If carousel, this is slides 2-5.

[CTA]       One specific ask: comment with a question, share their own war story,
            DM you, follow for next week.

[HASHTAGS]  3-5 max. #SupplyChain #DemandPlanning #AgenticAI #SOP #AIinSupplyChain
            Put them at the end, not woven in.
```

Algorithm rules (May 2026):
- Hook before the "...more" cutoff (~210 chars on desktop, ~140 on mobile).
- No external links in the post body — put the demo URL or GitHub link in the **first comment**, LinkedIn deprioritizes posts with outbound links.
- Reply to every comment in the first hour. The algorithm reads first-hour engagement as a quality signal.
- Carousels (PDF document posts) currently get the highest organic reach. Use them for the meaty technical content.
- Native video > YouTube embed. Keep demo videos under 90 seconds; first 3 seconds need to *show* the product, not your face.
- Post Tuesday–Thursday between 8-10am ET for B2B / supply chain reach.

## Post Drafts — All 6 Weeks

Voice rule for every post: write like a planner who codes, not like a thought leader. Specific numbers, specific tools, specific pain. No generic AI evangelism. No "the future of supply chain is..."

---

### Week 0 — Kickoff (text + diagram)

**Hook variants — pick one:**

> Variant A (recommended — credentials up front):
> Gartner says 60% of supply chain disruptions will be resolved by AI agents without human intervention by 2031.
> I plan demand for 10,000+ SKUs at a real retailer. I've been waiting for someone to *show* me what that looks like — not in a vendor demo, in code I can read.

> Variant B (story):
> Every Monday at 9am, I argue with a forecast.
> The forecast says one thing. My gut, my history, and the rep on the ground say another. Multiply that by 10,000 SKUs and that's the actual job of a demand planner.

> Variant C (contrarian):
> Most "agentic AI in supply chain" posts I read are written by people who've never planned a single SKU in their life.
> I plan 10,000+. Over the next 6 weeks I'm going to build the thing they keep slide-decking about.

**Body (after the hook):**

> So I'm going to build it.
>
> Project: Agentic S&OP Copilot. Public dataset (M5, 30,490 Walmart SKUs). Three agents in v1:
>
> → Forecast Agent — runs StatsForecast, reports MAPE and bias per SKU
> → Anomaly Agent — flags spikes, dips, and drift before your Monday S&OP
> → Root-Cause Agent — proposes *why*, ranked with evidence, never asserts
>
> Orchestrated with LangGraph. Deployed publicly so anyone can poke at it.
>
> One hard rule: the agents don't do arithmetic. Every number traces to a tool call. If I can't trust the output in an actual S&OP cycle, it doesn't ship.
>
> 6 weeks. Weekly updates with the messy middle. Demo + full code at the end.
>
> Curious — if you could ask your forecast one question in plain English on Monday morning, what would it be? Drop it below, I'll make sure v1 handles the top three.
>
> #SupplyChain #DemandPlanning #AgenticAI #SOP #AIinSupplyChain

**Asset:** the architecture diagram from `ARCHITECTURE.md`, rendered as a clean SVG/PNG. Square aspect ratio for mobile feed.

**First comment:** "Following the build week-by-week here. Repo will be public at launch."

---

### Week 1 — Data prep (7-slide carousel)

> **Slide 1 (cover, large text):**
> 30,490 SKUs.
> 5 years of data.
> Here's what your agent actually needs to plan.

> **Slide 2:**
> I spent week 1 prepping data, not building agents.
>
> This is the part vendors skip in their demos. They show you the chat.
> They never show you what's underneath.
>
> Here's what underneath actually looks like.

> **Slide 3 — The dataset:**
> M5 Forecasting (Walmart, public on Kaggle).
>
> • 30,490 SKUs
> • 1,941 days of daily sales
> • 10 stores across CA, TX, WI
> • Holiday + SNAP event flags
>
> Why this dataset: it's *real* retail. Not toy data. Not a SaaS demo deck.

> **Slide 4 — Why DuckDB, not Postgres, not Snowflake:**
> A demand-planning agent reads more than it writes. It groups, ranks, and aggregates.
>
> DuckDB does that locally in ~30ms. Zero infra. $0 to run.
>
> Anyone telling you an agent like this needs a vector DB is selling you a vector DB.

> **Slide 5 — Three tables. That's it:**
> sales(sku_id, store_id, date, units)
> calendar(date, is_holiday, holiday_name, snap_ca, snap_tx, snap_wi)
> forecasts(sku_id, date_made, point, lo80, hi80)
>
> The whole demo runs on three tables.

> **Slide 6 — One ugly truth:**
> Real sales data is full of zeros.
>
> Not "no demand" zeros. "We were stocked out" zeros. "We delisted" zeros. "The store closed for Thanksgiving" zeros.
>
> Your forecast model can't tell them apart.
> Your agent shouldn't pretend it can either.

> **Slide 7 (CTA):**
> Next week: building the Forecast Agent that knows what it doesn't know.
>
> Follow if you want to watch a planner build the AI he wishes someone would build for him.

**Caption (the post body that frames the carousel):**

> Everyone shows you the chat window. Nobody shows you what's underneath.
>
> Week 1 of building an agentic S&OP copilot in public: data prep. Here's what 30,490 SKUs and three tables look like when you're building an agent a planner would actually trust.
>
> Question for the planners reading: what's the *zero* in your data that quietly breaks your forecasts the most? Stockouts? Delists? Holidays the model never learned?
>
> #SupplyChain #DemandPlanning #AgenticAI

**First comment:** "Architecture doc + repo (in progress) → [link]"

---

### Week 2 — Forecast Agent (carousel + short demo GIF)

> **Hook (post body, before the carousel):**
> AI agents shouldn't do arithmetic.
>
> I built a forecasting agent this week. The LLM picks the model. The LLM explains the result. The LLM never multiplies a number.
>
> Here's why that rule is the whole product.

> **Slide 1 (cover):**
> An AI agent that does arithmetic is a bug, not a feature.

> **Slide 2 — What the agent does:**
> Planner types: "Forecast FOODS_3_090 next 28 days."
> Agent:
> 1. Picks AutoARIMA or ETS based on the SKU's seasonality
> 2. Calls StatsForecast (real Python, real math)
> 3. Reads back forecast + 80/95% intervals
> 4. Narrates in plain English
>
> What it does NOT do: any of the math.

> **Slide 3 — Why this matters:**
> LLMs hallucinate numbers. Not sometimes. Often.
> The bigger the planning question, the more confident the hallucination.
>
> If your agent reports "15,432 units" and that number didn't come from a tool call, it came from the LLM's vibes.
>
> Vibes don't belong in your S&OP deck.

> **Slide 4 — The fix is boring on purpose:**
> Tool: run_forecast(sku, horizon) → {point, lo80, hi80, lo95, hi95}
> Tool: get_accuracy(sku) → {mape, bias, rmse}
> Tool: get_history(sku, days) → raw units
>
> The LLM picks tools. The tools do math. The LLM narrates.
> Every number in the chat has a traceable origin.

> **Slide 5 — Results on M5 (100-SKU sample):**
> • Average MAPE: 23.4%
> • Bias: ±4.1% (no consistent over/under)
> • Cold-start SKUs (<60 days): excluded — the agent literally responds "I don't have enough history to forecast this one"
>
> That last bullet might be the most useful feature in the whole demo.

> **Slide 6 — GIF placeholder:**
> [90-second screen capture: type query → see chart + numbers + caveats]

> **Slide 7 (CTA):**
> Next week: Anomaly Agent.
> The agent that flags the SKUs about to ruin your Tuesday — before Monday's S&OP.

**Caption ask:**
> Question for the forecasters: what % of your "AI forecast" tools actually show you their MAPE and bias by SKU? Or do they just show you a number and ask you to trust it?

**First comment:** GitHub link

---

### Week 3 — Anomaly Agent (90-second native video)

**Video script (record screen + voiceover):**

> [0:00–0:03] *Screen: blank chat. Type appears:* "What needs my attention this week?"
> **VO:** "Every Monday at 9am, somebody in your S&OP meeting asks this question."

> [0:03–0:12] *Agent response appears: 7 SKUs, severity badges, short reason codes ("Spike +287% vs forecast", "Drift: 6-week negative bias").*
> **VO:** "Most planning systems answer it with a 47-tab report. This agent answers with seven SKUs."

> [0:12–0:35] *Zoom into first SKU. Historical chart, forecast line, red dot on the anomaly.*
> **VO:** "Statistical rules first — z-score against rolling mean, EWMA bias detection. The math is the math. The LLM never decides what counts as an anomaly."

> [0:35–0:55] *Split view: 30 raw statistical flags on the left, final list of 7 on the right.*
> **VO:** "Then the LLM ranks. Out of 30 statistical flags, which 7 actually matter to a planner this week? That's judgment. That's where the LLM earns its keep."

> [0:55–1:20] *Planner clicks one SKU. Trace panel slides in: each tool called, each value returned.*
> **VO:** "Every flag is traceable. The agent doesn't say 'this is anomalous because I think so.' It says 'z-score 3.1, rolling mean 412, last week 1,580 — here's the math.' Your S&OP team can audit every claim."

> [1:20–1:30] *Text overlay: "Anomaly Agent — shipped. Repo in comments. Next week: Root-Cause Agent."*
> **VO:** "Rules find candidates. LLM picks the ones that matter. Planner makes the call. That's what an honest agentic system looks like."

**Caption (this goes with the video):**
> Every Monday morning somebody in your S&OP meeting asks: "what needs my attention this week?"
>
> Most planning systems answer with a 47-tab report.
> This week I built an agent that answers with 7 SKUs.
>
> Demo above. Key design call: statistical rules find candidates, LLM ranks which ones matter, planner makes the final call. The LLM never decides what "anomalous" means — that's math. It only earns its keep on judgment.
>
> Every flagged SKU is fully traceable. No black box. No "the AI says so."
>
> What's the dumbest "anomaly" your current system flags every week that just wastes your time?
>
> #SupplyChain #DemandPlanning #AgenticAI #SOP

**First comment:** GitHub link

---

### Week 4 — Root-Cause Agent + Orchestrator (carousel)

> **Hook (post body):**
> "Why did sales spike?" is the most expensive question in your S&OP meeting.
>
> This week I built the agent that tries to answer it. Here's what's hard about it — and why most root-cause AI is dangerous.

> **Slide 1 (cover):**
> "Why did sales spike?"
> The most expensive question in S&OP — and the easiest one for an AI to get confidently wrong.

> **Slide 2 — The trap:**
> The LLM will *always* give you a plausible answer.
> That's not the same as a right answer.
>
> If your agent confidently says "demand spike caused by the holiday" and the real cause was "a competitor stocked out," you make a bad replenishment call and don't know why.
>
> Fix: rank candidates with evidence. Refuse to commit.

> **Slide 3 — What the agent checks:**
> For a flagged anomaly (SKU + date):
> • Was it a holiday or near one?
> • Was there a SNAP event in CA/TX/WI?
> • Did peer SKUs in the category also spike?
> • Was the previous week stocked out (artificial recovery)?
> • Is the day-of-week pattern normal?
>
> Each check is a tool call. Each tool call returns evidence.

> **Slide 4 — Sample output:**
> FOODS_3_090 spike on 2016-04-15:
>
> 1. (HIGH) SNAP event in CA + WI on this date
>    Evidence: SNAP flags = 1, peer SKUs averaged +156%
> 2. (MEDIUM) End-of-month replenishment pattern
>    Evidence: this SKU shows +30% on day 15 historically
> 3. (LOW) Random noise
>    Evidence: z-score 2.1 is moderate
>
> Never says "the cause is X." Always says "here are the candidates."

> **Slide 5 — Now: the orchestrator:**
> Three agents alone are useful.
> Three agents that talk to each other are *agentic*.
>
> LangGraph state machine routes user queries:
> • "What needs attention?" → Anomaly
> • "Why did X spike?" → Root-Cause
> • "Forecast X for 28d?" → Forecast
> • "What needs attention AND why?" → Anomaly → Root-Cause → composer
>
> [Diagram here.]

> **Slide 6 (CTA):**
> Next week: launch.
> Public demo URL. Full repo. "Here's what shipping agentic AI as a working demand planner actually looks like."
>
> Follow to catch it.

**Caption ask:**
> Honest question for the planners: how many of your "root cause" calls in Monday's meeting are actually causation vs. confident correlation? I've made both kinds of calls. The agent has to live with the same problem.

**First comment:** GitHub link

---

### Week 5 — LAUNCH (video + carousel) ⭐

This is the post that does the actual work. Spend extra time on it.

> **Hook:**
> 6 weeks ago I started building an agentic AI demand planner in public.
>
> Today, it's live. Anyone can use it.
> Code, demo, lessons learned — and the parts that are still broken — below.

> **Body:**
> What it does:
> A demand planner types a question in plain English. Three specialist agents collaborate to answer it.
>
> → "What needs my attention this week?" → 7 flagged SKUs in 4 seconds.
> → "Why did FOODS_3_090 spike on April 15?" → Ranked causes with evidence.
> → "Forecast HOBBIES_1_001 next 28 days with confidence intervals." → AutoARIMA result, narrated.
>
> Stack:
> • M5 Walmart dataset, 30,490 SKUs
> • LangGraph orchestrator, 3 specialist agents
> • StatsForecast for the actual math
> • Claude Sonnet 4.6 for routing + narration
> • DuckDB on a laptop, $0 infra
> • Streamlit deployed on Hugging Face Spaces
>
> What works:
> ✓ Every number traces to a tool call
> ✓ Agents refuse to forecast SKUs with insufficient history
> ✓ Root-Cause Agent ranks candidates, never asserts a single cause
> ✓ Sub-5-second response on most queries
>
> What doesn't (yet):
> ✗ No write-back to a planning system (o9, IBP, Kinaxis)
> ✗ Promo modeling is shallow (M5 has SNAP, not full promo data)
> ✗ No scenario agent — that's v2
>
> What I actually learned:
> The hard part of agentic AI in supply chain is *not* the agents. It's deciding what the agents are not allowed to do. The whole demo is held together by one rule: "the LLM never does arithmetic." Drop that rule and you have a chatbot that lies about your numbers. Keep it and you have a tool a planner could plausibly trust.
>
> Try it. Break it. Tell me what's missing.
> If you're hiring for supply chain AI roles — DMs are open.
>
> Demo + repo in the first comment.
>
> #SupplyChain #DemandPlanning #AgenticAI #SOP #AIinSupplyChain

**First comment:** "🔗 Demo: [HF Spaces URL] | Code: [GitHub URL]"

**Cross-post:** Same day, share the post on r/supplychain, r/MachineLearning (if rules allow), and the SCM subreddits. Email it to the 5 people in your network who should see it first.

---

### Week 6 — Retrospective (7-slide carousel)

> **Hook:**
> 5 lessons from building an agentic AI demand planner — as a working demand planner.
>
> Save this if you're thinking about doing the same.

> **Slide 1 (cover):**
> 5 lessons from 6 weeks of building agentic AI as a working demand planner.

> **Slide 2 — #1: The LLM is the worst part of the system.**
> It's also the most marketable. Every demo focuses on it.
>
> The real engineering is the tools — the DuckDB queries, the StatsForecast wrapper, the anomaly rules.
>
> Build the tools first. The LLM is the last 10%.

> **Slide 3 — #2: "Agents don't do arithmetic" is the single rule that made this trustworthy.**
> Every time I broke it (rounding, averaging, "just summarize the trend"), the output got worse and harder to audit.
>
> If you're building an agent for a regulated workflow: tools do math, LLM picks tools.

> **Slide 4 — #3: Statistical rules + LLM ranking beats pure-LLM detection.**
> I tried "just ask Claude to find anomalies in this data." It missed obvious ones and invented others.
>
> Switched to z-score rules generating candidates, LLM ranking which ones matter.
>
> Suddenly it worked. LLMs are good at judgment, bad at scanning.

> **Slide 5 — #4: Build in public is the project's biggest ROI feature.**
> The code took 6 weekends.
> The weekly posts took 1 hour each.
>
> The DMs from recruiters and other planners came from the posts — not the code.
>
> If you're building something for your career, the build is half the work. The narrative is the other half.

> **Slide 6 — #5: The hardest design decision was "when does the agent say I don't know?"**
> Most agents are optimized for confidence.
> Planners need agents optimized for *calibrated* confidence.
>
> "I don't have enough history" is a feature, not a failure.
>
> If your agent never says "I don't know," it's not a planning agent. It's a chatbot.

> **Slide 7 (CTA):**
> What's next:
> v2 ideas → scenario agent (what-if promos), writeback to o9/IBP via mock connector, multi-store view.
>
> If you want the repo, want to build on it, or want to talk shop — DMs open.
>
> Code + demo in the first comment.

**Caption (post body before the carousel):**
> 6 weeks ago I said I was going to build an agentic AI demand planner in public.
> 5 lessons from doing it — most of them not what I expected.

**First comment:** GitHub + demo links

## Engagement Playbook

Spend 20 minutes a day, 5 days a week, doing **just** these things:

1. Comment thoughtfully on 5 posts in your niche. Look for posts from:
   - Lora Cecere, Andrew Pery, Pierre-Francois Thaler, Sarah Barnes-Humphrey, Brittain Ladd
   - Anyone from Kinaxis, Blue Yonder, o9, SAP IBP, Anaplan, RELEX talking about AI
   - Hiring managers at supply chain / AI-forward companies
2. Reply to every comment on your own posts for the first 4 hours after posting.
3. Once a week, DM one connection a non-spammy "saw your post, here's a thought" message.

Don't tag SAP / Kinaxis / o9 in your posts unless you have a direct relationship — it reads as ladder-climbing and can suppress reach. Reference them in the body instead.

## Metrics to Track

Keep it simple — log these in a Google Sheet after each post:

| Date | Post | Format | Impressions | Reactions | Comments | DMs | Followers gained | Notes |

What "good" looks like for someone with <2K followers in this niche:
- 1K+ impressions = solid
- 5K+ impressions = the post worked
- 10K+ = went viral for the niche
- 2-3 quality DMs from recruiters or peers per launch-quality post = the actual ROI

## What to Do With the Inbound

When recruiters / hiring managers DM, do **not** reply with your resume. Reply with:
1. Thanks for reaching out
2. One specific question about their team / their AI strategy
3. Offer a 20-min call

This converts 3-5x better than blasting the resume, and it filters out the recruiters who are just net-fishing.

## Open questions to revisit at week 4

- Is there a v2 angle worth pre-announcing in the launch post (scenario agent, writeback to o9)?
- Should we open-source the repo, or keep it closed and offer a hosted demo? (Open-source = more reach; closed = more DMs.)
- Is there a podcast or newsletter (e.g., Supply Chain Now, The Logistics of Logistics) worth pitching after week 6?
