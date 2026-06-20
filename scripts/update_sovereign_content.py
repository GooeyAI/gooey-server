#!/usr/bin/env python3
"""Regenerate col-text and patch sovereign.html from updated doc content."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "static/sovereign/sovereign.html"
IMG = "/static/sovereign/images"

COL_TEXT = f"""
  <div class="col-text">

    <section class="step" id="section-abstract" data-vis="art-abstract" data-section="Abstract">
      <span class="step-eyebrow">Abstract</span>
      <p class="lead">Middle power nations trail the US &amp; China in AI compute and talent but together they can thrive with sovereign AI that is beneficial to local communities and businesses; reflective of our local languages, culture, and productivity needs; not extractive, surveilled nor suspendable by other nations; and positively impactful with benefits and expertise that can easily spread.</p>
      <p>We argue middle powers — including India, UK and the nations of Europe, SE Asia, Africa, Latin America — should cooperate to influence AI benchmarks; publish datasets to improve both private and open source models; invest in locally deployable, hot-swappable models that are verified and fine-tunable; and support distributed efforts to train models, and mandate standards that encourage commoditization and abstraction to spread AI workflows that advance SDGs and empower every nation.</p>
    </section>

    <section class="step" id="section-sovereign-desire" data-vis="img-desire" data-section="The sovereign desire">
      <span class="step-eyebrow"><span class="n">01</span> The sovereign desire</span>
      <h2>The sovereign desire</h2>
      <p>Amidst the global AI race, Middle powers face immense pressure to forge their own digital destiny. The risk is concrete: rising integration and ubiquity of AI in private and public infrastructure implies that systems running local businesses, schools, hospitals, banks, and government services will be trained on non-local norms and languages; susceptible to be repriced, surveilled, or suspended by foreign governments and corporations. With the June 2026 US directive suspending access to Anthropic's latest Claude Fable 5 and Mythos models to all foreign nationals, this is no longer a distant reality. Frontier model capabilities are increasingly viewed as national security assets, framed not as software but strategic infrastructure. Increasingly, dependence on a foreign AI ecosystem means inviting structural vulnerability.</p>
      <p>For middle powers, AI sovereignty thus has never been more urgent. We argue that the path forward is not what some political rhetoric suggests: complete self-sufficiency across the entire AI value chain — energy, chips, infrastructure, models and applications. That path is neither economically realistic, desirable nor necessary.</p>
    </section>

    <section class="step" id="section-outgunned" data-vis="img-power" data-section="Current AI Landscape">
      <span class="step-eyebrow"><span class="n">02</span> Current AI Landscape</span>
      <h2>But let's face it. We're outgunned.</h2>
      <p>Let's look at the numbers. When it comes to <a href="https://epoch.ai/data/data-centers?view=graph&tab=cost&colorCategorization=primaryUser" target="_blank" rel="noopener">compute spend</a> — the energy, real estate, chips and data centers driving AI — the US and China are orders of magnitude ahead of any other country.</p>
    </section>

    <section class="step" data-vis="chart-dc" data-section="Current AI Landscape">
      <span class="step-eyebrow"><span class="n">02</span> Current AI Landscape</span>
      <p>The single largest planned US site — Microsoft's Fairwater Wisconsin (3,328&nbsp;MW, primary user OpenAI) — alone rivals the entire national AI budget of most middle powers.</p>
    </section>

    <section class="step" data-vis="chart-pub" data-section="Current AI Landscape">
      <span class="step-eyebrow"><span class="n">02</span> Current AI Landscape</span>
      <p>AI talent &amp; research is similarly concentrated; China and the US are expected to publish more than half of all AI papers in 2026, with the 27 EU nations publishing 11.3% and India at 8.4%.</p>
      <p>A 2026 Economist <a href="https://www.economist.com/interactive/science-and-technology/2026/03/25/china-is-winning-the-ai-talent-race" target="_blank" rel="noopener">report</a> reveals that Chinese organisations account for 37% of world's leading AI researchers, with U.S. organisations trailing with a close 32%.</p>
    </section>

    <section class="step" data-vis="img-wright" data-section="Current AI Landscape">
      <span class="step-eyebrow"><span class="n">02</span> Current AI Landscape</span>
      <p>And from this collective but under-resourced stance, we recall Robert Wright.</p>
      <div class="pull pull-wright"><p>"<span class="wright-red">Zero-sum threats</span> create<br><span class="wright-teal">non-zero-sum incentives</span>."</p><div class="by">— Robert Wright, <i>Nonzero</i></div></div>
    </section>

    <section class="step" data-vis="img-cooperation" data-section="Current AI Landscape">
      <span class="step-eyebrow"><span class="n">02</span> Current AI Landscape</span>
      <p>While independent nations may not be able to effectively compete and sway the AI market, like-minded coordinated states can. Instead of building walled gardens, middle power nations can work together on shared infrastructure and standards, to help create digital foundations that build on everyone's progress.</p>
    </section>

    <section class="step step-hscroll" id="section-goals" data-vis="hcards-goals" data-section="Our goals">
      <span class="step-eyebrow"><span class="n">03</span> Our goals</span>
      <h2>Our goals for AI sovereignty</h2>
      <p>Four properties define sovereign AI worth building. It must be:</p>
      <div class="hscroll-track" tabindex="0" aria-label="Goals — scroll horizontally">
        <article class="hcard">
          <img src="{IMG}/image13.png" alt="Beneficial to local citizens, communities, and businesses"/>
          <h3>Beneficial to local citizens, communities, and businesses</h3>
          <p>Sovereign AI must benefit each nation's people, society and economy, while mitigating harms and risks.</p>
        </article>
        <article class="hcard">
          <img src="{IMG}/image6.png" alt="Reflective of local languages, culture, and productivity needs"/>
          <h3>Reflective of local languages, culture, and productivity needs</h3>
          <p>Sovereign AI must not only speak the languages of each nation, but also reflect its broader visual, audio and cultural traditions. It must enhance the productivity needs of a nation. A model that can solve English coding challenges, but can't provide reasonable farming advice in Indic languages when 65% of <a href="https://www.pib.gov.in/PressReleseDetailm.aspx?PRID=1939473&amp;reg=3&amp;lang=2" target="_blank" rel="noopener">Indians work in agriculture</a> and related industries, by definition can't be very useful to most Indians.</p>
        </article>
        <article class="hcard">
          <img src="{IMG}/image17.png" alt="Not extractive, surveilled nor suspendable by other nations"/>
          <h3>Not extractive, surveilled nor suspendable by other nations</h3>
          <p>The greatest productivity leap of this century cannot come with a foreign tax on every digital interaction to the powers that dominated the last one. Sovereign AI implies freedom from citizen conversations being subject to <a href="https://www.bbc.co.uk/news/articles/ckge8zkr0d2o" target="_blank" rel="noopener">foreign surveillance</a> and government communication tools that can't be suspended with geopolitical shifts (see EU prosecutor <a href="https://www.euractiv.com/news/international-criminal-court-to-ditch-microsoft-office-for-european-open-source-alternative/" target="_blank" rel="noopener">Karim Khan's suspended Microsoft Office account</a>). Sovereign telecommunications can be a guide here too; nations don't pay US or Chinese companies to connect every domestic phone call. We should demand the same of AI.</p>
        </article>
        <article class="hcard">
          <img src="{IMG}/image8.png" alt="Positively impactful with benefits and expertise spreading"/>
          <h3>Positively impactful with benefits and expertise spreading</h3>
          <p>Finally, sovereign AI must push forward each country's and the <a href="https://sdgs.un.org/goals" target="_blank" rel="noopener">UN's Sustainable Development Goals</a>. And when we find AI hardware, software and solutions that work responsibly and sustainably, they should easily spread, with each country able to quickly learn from and sell new AI products to each other.</p>
        </article>
      </div>
    </section>

    <section class="step" id="section-cooperate" data-vis="art-levers" data-section="How they cooperate">
      <span class="step-eyebrow"><span class="n">04</span> How they cooperate</span>
      <h2>So how do middle powers cooperate for AI sovereignty?</h2>
      <p>Four levers, where cooperation creates real leverage. Each builds on the last: influence the benchmarks, direct the datasets, foster deployable models, and spread impactful workflows.</p>
    </section>

    <section class="step" id="section-benchmarks" data-vis="chart-gemini" data-section="1 · Benchmarks">
      <span class="step-eyebrow"><span class="n">Lever 01</span> Benchmarks</span>
      <h2>Influence the AI benchmarks</h2>
      <p>What gets measured, gets built. Every AI lab is pouring billions into topping an ever-evolving and frankly highly geeky set of benchmarks attempting to evaluate which AI model beats the others.</p>
      <div class="pull"><p>"My engineers will work 25 hours per day to score a tenth of a point higher on a popular eval."</p><div class="by">— <a href="mailto:dorukc@google.com" target="_blank" rel="noopener">Doruk Caner</a>, Director at DeepMind</div></div>
      <p>Popular AI benchmarks published by model makers as a proof of their AI supremacy tend to reflect the fields that produce AI engineers and over-index on arcane knowledge.</p>
    </section>

    <section class="step" data-vis="chart-glm" data-section="1 · Benchmarks">
      <span class="step-eyebrow"><span class="n">Lever 01</span> Benchmarks</span>
      <p>Benchmarks such as <a href="https://agi.safe.ai/" target="_blank" rel="noopener">Humanity's Last Exam</a>, <a href="https://arcprize.org/arc-agi/2" target="_blank" rel="noopener">ARC-AGI2</a> and <a href="https://epoch.ai/benchmarks/gpqa-diamond" target="_blank" rel="noopener">GPQA Diamond</a> test deep knowledge and skills in math, programming and the most lucrative professional services of the West — medicine, finance and law.</p>
      <p>The opportunity for middle powers is to create and proselytize benchmarks that represent their specific national productivity needs. E.g. Wouldn't it be great if Google and OpenAI loudly proclaimed the quality of their smallholder agriculture advice — a field that 42% of the world's households (<a href="https://documents1.worldbank.org/curated/en/587251468175472382/pdf/41455optmzd0PA18082136807701PUBLIC1.pdf" target="_blank" rel="noopener">World Bank</a>) rely on for their primary income and is changing dramatically with wars, increased fertilizer prices and climate change — vs just PhD level math?</p>
    </section>

    <section class="step" id="section-datasets" data-vis="img-dataset-trio" data-section="2 · Datasets">
      <span class="step-eyebrow"><span class="n">Lever 02</span> Datasets</span>
      <h2>Directing datasets</h2>
      <p>All AI models are reflections of their training datasets. AI model makers trained their models on <a href="https://commoncrawl.org/" target="_blank" rel="noopener">much of the Internet</a>. Hence, the cultures, languages and nations that dominated the imagery, text and increasingly video of the early 2020s Internet are those that AI now generates for everyone.</p>
      <p>The problem that arises is one of continued cultural and economic hegemony manifested in AI model performance along three axes.</p>
    </section>

    <section class="step" data-vis="art-axes" data-section="2 · Datasets">
      <span class="step-eyebrow"><span class="n">Lever 02</span> Datasets</span>
      <h3>Axis 01 — Language</h3>
      <p>English, EU and Chinese languages dominate much of the world's Internet text and their speakers command most of the world's richest economies. Hence, these languages tend to be reasonably well understood and generated in text and voice. Low-resource languages spoken by less than 100 million people traditionally have not garnered the datasets nor requisite market potential for AI makers to focus on, and hence, the digital divide exacerbates, with low-resource language speakers engaging with often addictive social media, without the economic and knowledge access of productivity-enhancing AI.</p>
    </section>

    <section class="step" data-vis="img-culture7" data-section="2 · Datasets">
      <span class="step-eyebrow"><span class="n">Lever 02</span> Datasets</span>
      <h3>Axis 02 — Culture</h3>
      <p>This inequity in AI generated is detectable in language but often ridiculous in images. Ask image models for culturally specific visual styles and they may flatten, confuse, or Westernize them. Ask for local people, clothing, architecture, crops, festivals, or classroom settings and AI models often return the Western gaze on Global South culture — see Kamala Harris in Bollywood dress — rather than indigenous cultural styles.</p>
      <p>This problem is particularly urgent as many emerging countries seek to equip their students with AI skills, pushing tools such as Google Slides and M365 into classrooms, with students then using image generation models that often don't represent local cultures well. These misrepresentations — images and the textual descriptions around them — then become training data for future iterations of AI models, baking in deeply flawed representations of Global South cultures.</p>
      <p>To build more inclusive AI, middle powers should cooperate on datasets that cover four areas.</p>
    </section>

    <section class="step" data-vis="img-axis-domain" data-section="2 · Datasets">
      <span class="step-eyebrow"><span class="n">Lever 02</span> Datasets</span>
      <h3>Axis 03 — Domain understanding &amp; reasoning</h3>
      <p>The major AI labs have spent billions of dollars to train AI on the most valuable Western professions including programming, finance, medicine and law. Thousands of person-years of coders, accountants, doctors and lawyers have been spent rating and annotating AI generated, mostly English responses and these efforts have achieved incredible gains in step-by-step "thinking" and AI performance in the fields mostly US tech firms believed would be the easiest to monetize. Those industries and markets far from Beijing and Silicon Valley have seen far less investment and hence, the potential impact of AI in these non-lucrative fields isn't being met.</p>
    </section>

    <section class="step" data-vis="img-kin" data-section="2 · Datasets">
      <span class="step-eyebrow"><span class="n">Lever 02</span> Datasets · Languages</span>
      <h3>Languages</h3>
      <p>Speech, text, dialects, code-switching, and local scripts. The good news here is that low-resource language investments made by the Gates Foundation, the World Bank, Google and Meta and others appear to be working. As we at <a href="https://gooey.ai/language-evaluation" target="_blank" rel="noopener">Gooey.AI can attest</a>, text and speech recognition AI performance on low-resource language is improving dramatically in both private and the latest open source models.</p>
    </section>

    <section class="step" data-vis="img-culture8" data-section="2 · Datasets">
      <span class="step-eyebrow"><span class="n">Lever 02</span> Datasets · Culture</span>
      <h3>Culture</h3>
      <p>Custodians of local indigenous cultures (including libraries, museums and universities) have a valuable role to play in digitizing, labeling and publishing under-represented culture in its broadest forms — including visual art, music, dance, film, handwriting, scripts — so that all generative AI models can accurately create new forms of culture.</p>
      <h3>Productivity needs</h3>
      <p>The actual tasks people perform in agriculture, health, education, government, and business.</p>
      <h3>Domain-specific reasoning</h3>
      <p>Not just "Does the model speak my language?" but "Does it give expert and locally informed advice to the problems my community faces?" This should include critical and under-resourced datasets in areas critical to each country. Eg 1000s of labeled images taken on cheap Android phones of ailing plants.</p>
    </section>

    <section class="step" id="section-deployable" data-vis="art-lockin" data-section="3 · Deployable models">
      <span class="step-eyebrow"><span class="n">Lever 03</span> Deployable models</span>
      <h2>Foster locally deployable frontier models</h2>
      <p style="font-family:var(--gy-font-serif);font-style:italic;color:var(--gy-ink-muted);font-size:20px">No country or vendor lock-in.</p>
      <p>When cell phones spread to every country, nations did not have to pay a tax to the US or China with every phone call. They could also be reasonably confident that their citizens were not being surveilled en masse by a foreign power with every domestic conversation. Compare this to private usage today with ChatGPT, Gemini or Claude. The data and dollars of every BigTech AI conversation flows to US companies, subject to the <a href="https://en.wikipedia.org/wiki/CLOUD_Act" target="_blank" rel="noopener">Cloud Act</a> and <a href="https://www.bbc.co.uk/news/articles/ckge8zkr0d2o" target="_blank" rel="noopener">FISA</a>, with rising token costs as models improve their intelligence. Similar data and dollar leakage occurs with usage of <a href="https://deepseek.com" target="_blank" rel="noopener">deepseek.com</a>.</p>
      <p>Jensen Huang's <a href="https://blogs.nvidia.com/blog/world-governments-summit/" target="_blank" rel="noopener">calls for nations</a> to build their own sovereign data centers has resonated (there's a reason Nvidia is the <a href="https://en.wikipedia.org/wiki/List_of_public_corporations_by_market_capitalization" target="_blank" rel="noopener">world's most valuable company</a>) and though middle powers can't spend $500 billion on data centers, they can spend millions and once they do, they will want to monetize these data center investments.</p>
      <p>Training frontier AI models <a href="https://www.iea.org/reports/energy-and-ai/energy-demand-from-ai" target="_blank" rel="noopener">demand</a> energy equivalents to the needs of entire countries and most middle powers simply haven't made the investments required to be even distant players in this space. BUT they can run inference — on mobiles, personal computers and data center GPUs — so long as there are good enough pre-trained models with customer demand. Hence, middle powers must organize markets to ensure these sovereign deployable AI models are viable intelligence contenders.</p>
    </section>

    <section class="step" data-vis="art-actors" data-section="3 · Deployable models">
      <span class="step-eyebrow"><span class="n">Lever 03</span> Deployable models</span>
      <p>This is where the differing assets and aspirations of other powers are relevant:</p>
      <h4>The United States</h4>
      <p>The US (and its BigTech giants that now make up more than <a href="https://www.cnbc.com/2025/10/22/your-portfolio-may-be-more-tech-heavy-than-you-think.html" target="_blank" rel="noopener">30% of the S&amp;P 500</a>) have business models based on private inference, betting that companies and governments of the world will spend for most intelligent AI models from US-based firms and data centers serving inference tokens via private models. Meta was the only BigTech firm publishing frontier capable, sovereign data center deployable models but with <a href="https://techcrunch.com/2025/11/11/metas-chief-ai-scientist-yann-lecun-reportedly-plans-to-leave-to-build-his-own-startup/" target="_blank" rel="noopener">Yann LeCun's departure</a>, this appears to have slowed. Google is publishing capable <a href="https://deepmind.google/models/gemma/" target="_blank" rel="noopener">Gemma models</a>, but their best-in-class performance is limited to low-parameter models (intended to increase demand for new Android devices) while the most intelligent large models — <a href="https://deepmind.google/models/gemini/" target="_blank" rel="noopener">Gemini</a> — are not sovereign deployable. Nvidia has a strong interest in selling sovereign AI and hence, may end up being the US company willing to invest billions in capable open source models like Nemotron Ultra.</p>
      <h4>China</h4>
      <p>China leads the world in manufacturing, has the 2nd best compute resources and strategically wants to disrupt US AI with open-source, open-weight AI models. China's strategy is to leverage its significant hardware advantage and embed open source AI into every piece of electronics it sells. China's tech giants such as <a href="https://www.moonshot.ai/" target="_blank" rel="noopener">Moonshot AI</a>, <a href="https://www.tencent.com/" target="_blank" rel="noopener">Tencent</a>, <a href="https://z.ai" target="_blank" rel="noopener">Z.ai</a> and <a href="https://www.alibaba.com/" target="_blank" rel="noopener">Alibaba</a> are currently creating the world's most intelligent AI models that can be deployed in sovereign data centers.</p>
      <h4>Middle powers</h4>
      <p>Middle powers on the upper end of the AI spectrum — India, the UK, the EU, Korea — are attempting to create their own LLMs but none have fine-tuned nor created models with that later achieved significant traction.</p>
    </section>

    <section class="step step-hscroll" data-vis="hcards-recs" data-section="3 · Recommendations">
      <span class="step-eyebrow"><span class="n">Lever 03</span> Recommendations</span>
      <h3>Recommendations</h3>
      <div class="hscroll-track" tabindex="0" aria-label="Recommendations — scroll horizontally">
        <article class="hcard">
          <img src="{IMG}/image16.png" alt="Foster instant swapability"/>
          <h3>Foster instant swapability</h3>
          <p>Rather than spending billions on indigenous AI tech stacks, we believe middle powers should enable open, modular AI architectures that preserve choice and substitutability by collaborating on technical standards. The goal is AI model and provider commoditization. Success should be gauged by how easily applications can be moved across providers and models. As David Eaves and Mike Brackon <a href="https://www.techpolicy.press/the-path-to-a-sovereign-tech-stack-is-via-a-commodified-tech-stack/" target="_blank" rel="noopener">argue</a>, "Domination by a local champion, free to extract rents, may be a path to greater autonomy, but it is unlikely to lead to increased competitiveness or greater global influence." By championing open-source middleware, abstraction and orchestration layers, middle powers can build an architecture of choice where swappability is real.</p>
        </article>
        <article class="hcard">
          <div class="hcard-media">
            <img src="{IMG}/image40.png" alt="Clarote &amp; AI4Media — Better Images of AI"/>
            <div class="hcard-cite"><a href="https://betterimagesofai.org" target="_blank" rel="noopener">Clarote &amp; AI4Media</a> · <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noopener">CC-BY 4.0</a></div>
          </div>
          <h3>Develop tools to detect and undo model bias and misinformation</h3>
          <p>AI models do not come with a clean slate; they instill their own cultural worldviews and ideologies — and for Chinese trained models, this means importing histories inline with Chinese Communist Party's (CCP) guidelines. Middle powers must be able to reinsert history like <a href="https://www.perplexity.ai/api-platform/resources/open-sourcing-r1-1776" target="_blank" rel="noopener">Perplexity's 1776 model</a> did by taking DeepSeek R1 as a base and stripping documented CCP censorship and <a href="https://www.abc.net.au/news/2025-06-04/beijing-ai-and-censors-erase-tiananmen-square-massacre/105370772" target="_blank" rel="noopener">re-adding suppressed historical records</a>. Additionally, there is a credible risk that frontier models may deliberately misdirect strategically sensitive queries. Research on detection and reversal of these misdirections currently remain nascent; middle powers must collaborate to fill this lacuna.</p>
        </article>
        <article class="hcard">
          <div class="hcard-media">
            <img src="{IMG}/image12.png" alt="Clarote &amp; AI4Media — Better Images of AI"/>
            <div class="hcard-cite"><a href="https://betterimagesofai.org" target="_blank" rel="noopener">Clarote &amp; AI4Media</a> · <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noopener">CC-BY 4.0</a></div>
          </div>
          <h3>Invest in distributed model training and cheaper inference</h3>
          <p>Rather than matching the compute of the US and China, middle powers can redirect their investments to distributed training. Recent advances in distributed machine learning (e.g. <a href="https://deepmind.google/blog/decoupled-diloco/" target="_blank" rel="noopener">Google DeepMind's DiLoCo framework</a>) demonstrate how frontier models can be trained across geographically dispersed computing datacenters. We've seen this play out in airlines, with Airbus mounting a credible alternative to Boeing through a cooperative multi-country effort. Additionally, middle powers should <a href="https://www.youtube.com/watch?v=xmkSf5IS-zw" target="_blank" rel="noopener">invest in cheaper inference</a>, so they can run top AI models on their own data centers more efficiently too.</p>
        </article>
        <article class="hcard">
          <div class="hcard-media">
            <img src="{IMG}/image41.png" alt="Clarote &amp; AI4Media — Better Images of AI"/>
            <div class="hcard-cite"><a href="https://betterimagesofai.org" target="_blank" rel="noopener">Clarote &amp; AI4Media</a> · <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noopener">CC-BY 4.0</a></div>
          </div>
          <h3>Encourage small, capable models designed for commodity hardware</h3>
          <p>Middle powers should facilitate the creation of effective, locally deployable AI models that can run not only on sovereign data centers, but also on cheap, ubiquitous hardware. Here, we have natural ecosystem allies on mobiles and personal computers costing $1,000–$5,000 — Nvidia, Intel, Apple, Microsoft and the largely Taiwanese and Chinese computer hardware industry all have business model alignment to create increasingly capable AI models that run on commodity hardware.</p>
        </article>
      </div>
    </section>

    <section class="step" data-vis="art-edge" data-section="3 · Deployable models">
      <span class="step-eyebrow"><span class="n">Lever 03</span> Commodity hardware</span>
      <h4>Mobiles</h4>
      <p>AI on the phone can enable offline speech understanding as its most relevant near-term use case. Google, Apple and the mostly Chinese-based handset ecosystem will continue to invest here (e.g. Google's <a href="https://blog.google/innovation-and-ai/technology/developers-tools/gemma-4/" target="_blank" rel="noopener">Gemma 4 Effective</a> series) because they hope it will drive demand for new mobile purchases. With sufficient localized datasets of low-resource languages, we hope to see offline speech understanding available to most languages in the coming 12–18 months, enabling everyone to harness humanity's collective knowledge and reasoning, regardless of their literacy or connectivity.</p>
      <h4>High-end laptops, Mac Mini and Surface Ultra</h4>
      <p>Personal computers — costing $1,000–$5,000 — can be effective hardware to run AI sovereignly in the years ahead. <a href="https://www.youtube.com/watch?v=wykPErJ8M-8" target="_blank" rel="noopener">Apple</a> has bet their future on improving prosumer hardware for AI (e.g. the upcoming <a href="https://like2byte.com/mac-mini-m4-local-llm-server-agency/" target="_blank" rel="noopener">Mac Minis</a>) and Microsoft hopes to re-energize PC purchases with AI workhorses like the Surface Ultra.</p>
    </section>

    <section class="step" id="section-workflows" data-vis="img-hotswap" data-section="4 · Spread workflows">
      <span class="step-eyebrow"><span class="n">Lever 04</span> Spread workflows</span>
      <h2>Spread impactful AI via open source software, markets &amp; workflows</h2>
      <p>The model landscape is moving quickly. OpenAI, Google, Anthropic, Mistral, Qwen, DeepSeek, Kimi, and other model families keep changing the frontier of cost, quality, latency, multilingual support, and deployability.</p>
      <p>Many use-cases worldwide benefit from the frontier intelligence of US and China based AI companies and often the data privacy risks and costs are worth it.</p>
      <p>The key is designing for substitutability. When AI systems are built on open, interoperable standards, institutions retain the practical ability to switch providers as the landscape shifts.</p>
      <p>Hence, we should facilitate hot-swapping: the ability to easily constantly evaluate and then switch to whichever model is best, fastest, cheapest, safest, or most sovereign for the task. The point is not to reject private frontier models; but rather to avoid dependency on any single provider and encourage competition.</p>
      <p>We should be able to easily run, fork and usability test AI solutions in the cloud — where the global marketplace of hyperscalers can keep costs lower — and quickly deploy them to sovereign data centers if needed.</p>
    </section>

    <section class="step" id="section-sdg" data-vis="img-landscape" data-section="Shared workflows">
      <span class="step-eyebrow"><span class="n">05</span> Shared workflows</span>
      <h2>From models to shared workflows that move SDGs</h2>
      <p>Sovereignty should not stop at national capacity. It should improve the speed at which useful AI spreads among public-interest organizations. This is where open-source infrastructure and reusable AI workflows matter.</p>
      <p>At Gooey.AI, we think of an AI workflow as a human-readable recipe: prompts, model choices, tools, APIs, knowledge documents, analytics, and importantly bespoke evaluations bundled around a real use case. A workflow can be easily inspected, improved, forked, translated, and redeployed.</p>
      <p>That matters because the best AI solutions for global impact must be patterns that spread. If a farmer advisory workflow works in one region, another organization should be able to inspect it, adapt it to local crops and languages, test it against local benchmarks, and deploy it through WhatsApp, SMS, voice, or web.</p>
    </section>

    <section class="step" id="section-farmers" data-vis="img-dg" data-section="Sidebar · Farmers">
      <span class="step-eyebrow"><i class="fa-regular fa-bookmark"></i> Sidebar · A story of farmers and AI</span>
      <h2>"We built in a day what we'd worked on for three months"</h2>
      <p><b><a href="https://help.gooey.ai/farmerchat" target="_blank" rel="noopener">Farmer.Chat</a></b> is one example of what this looks like in practice. Built from the wisdom of thousands of <a href="https://digitalgreen.org/" target="_blank" rel="noopener">Digital Green</a>'s farmer <a href="https://www.youtube.com/user/digitalgreenorg" target="_blank" rel="noopener">videos</a>, farmers can ask a multilingual WhatsApp or Android bot questions by text or voice, upload photos of ailing plants and receive answers in their language.</p>
    </section>

    <section class="step" data-vis="img-chat" data-section="Sidebar · Farmers">
      <span class="step-eyebrow"><i class="fa-regular fa-bookmark"></i> Sidebar · Farmers</span>
      <p>Farmer.Chat was demo'd at the 2023 UN General Assembly's Science Panel and garnered press including an <a href="https://openai.com/index/digital-green/" target="_blank" rel="noopener">OpenAI case-study</a>. Importantly, <a href="https://gooey.ai/copilot/farmerchat-via-gpt-4o-nuwsqmzp" target="_blank" rel="noopener">Farmer.Chat's AI workflow recipe</a> — the LLM instructions, model settings, analysis scripts, knowledge documents — were available so that other organizations serving smallholder farmers could find, customize and re-deploy the AI recipe for their own markets and users. <a href="https://opportunity.org/" target="_blank" rel="noopener">Opportunity International</a> — an 80 year old NGO with offices in 33 countries — quickly forked and deployed the agriculture chatbot in Malawi (as <a href="https://unlocked.microsoft.com/opportunity-international/" target="_blank" rel="noopener">Ulangizi</a>), Ghana (as <a href="https://www.dbg.com.gh/opportunity-international-development-bank-ghana-launch-a-pilot-ai-chatbot-for-smallholder-farmers/" target="_blank" rel="noopener">Farmer AI</a>), and Kenya (as <a href="https://opportunity.org/news/press-releases/opportunity-international-and-safaricom-launch-new-ai-chatbot-for-smallholder-farmers" target="_blank" rel="noopener">DigiFarm</a> with Safaricom).</p>
      <div class="pull"><p>"We built in a day what we had been working on for three months."</p><div class="by">— Paul Essene, Opportunity International</div></div>
      <p style="margin-top:18px">If a mental health triage assistant works for one public health context, another should be able to fork it, replace the knowledge base, adjust safety rules, and run local evaluations. This is what the Wellcome Trust is supporting with their <a href="https://mexa.app/accelerator" target="_blank" rel="noopener">mental-health accelerator</a>, in partnership with Google and Gooey.AI.</p>
    </section>

    <section class="step" id="section-conclusion" data-vis="art-conclusion" data-section="Conclusion">
      <span class="step-eyebrow">Conclusion</span>
      <h2>Sovereignty through cooperation</h2>
      <p>AI sovereignty is not digging a moat around national AI systems. It is about ensuring that AI is beneficial, reflective, non-extractive, and open enough to spread.</p>
      <p>Middle powers need to cooperate where cooperation creates leverage:</p>
    </section>

  </div>
"""

SCROLLY_FINALE = """
<div class="scrolly scrolly-finale">

  <div class="col-text">

    <section class="step" data-vis="art-final" data-section="Conclusion">
      <span class="step-eyebrow">Conclusion</span>
      <p>The future of AI will not only be decided in frontier labs and data centers. It will also be decided in classrooms, clinics, farms, public agencies, cultural institutions, and civil society organizations that ask a more grounded question:</p>
      <h2 style="font-style:italic;color:var(--gy-ink)">"Does this AI help our people, in our language, on our terms?"</h2>
      <p style="font-family:var(--gy-font-serif);font-size:22px;color:var(--gy-orange)">That is the sovereignty worth building.</p>
    </section>

  </div>
</div>
"""

FIGLAYERS = f"""
      <figure class="figlayer" data-vis="art-abstract"><div id="globeDockAnchor" aria-hidden="true"></div></figure>
      <figure class="figlayer" data-vis="img-desire"><img src="{IMG}/image18.png" alt="The sovereign desire — structural vulnerability of foreign AI dependence"/></figure>
      <figure class="figlayer" data-vis="img-power"><img src="{IMG}/image12.png" alt="Power/Profit by Claire &amp; AI4Media — Better Images of AI"/><figcaption><a href="https://betterimagesofai.org" target="_blank" rel="noopener">Power/Profit by Claire &amp; AI4Media</a> · <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noopener">CC-BY 4.0</a></figcaption></figure>

      <figure class="figlayer" data-vis="chart-dc">
        <div class="chartwrap"><div class="chart-brand"><img src="https://www.google.com/s2/favicons?domain=epoch.ai&amp;sz=32" width="22" height="22" alt=""/><span>US Frontier Data Centers · <a href="https://epoch.ai" target="_blank" rel="noopener">Epoch.AI</a></span></div><div class="chart-legend" id="dcLegend"></div>
        <svg class="csvg" id="dcChart" viewBox="0 0 760 560" role="img" aria-label="Frontier data center cost scatter"></svg></div>
        <figcaption>Build cost vs. operational date, bubble ≈ power. Hover any project. Cost figures are public estimates.</figcaption>
      </figure>

      <figure class="figlayer" data-vis="chart-pub">
        <div class="chartwrap"><div class="chart-brand"><img src="https://www.google.com/s2/favicons?domain=oecd.ai&amp;sz=32" width="22" height="22" alt=""/><span>AI publications by country · <a href="https://oecd.ai" target="_blank" rel="noopener">OECD</a></span></div><div class="chart-legend" id="pubLegend"></div>
        <svg class="csvg" id="pubChart" viewBox="0 0 760 520" role="img" aria-label="AI publications by country"></svg></div>
        <figcaption>Share of the world's AI publications (%), 2016–2026. Click a country to toggle.</figcaption>
      </figure>

      <figure class="figlayer" data-vis="img-wright"><img src="{IMG}/image1.png" alt="Nonzero: The Logic of Human Destiny by Robert Wright"/><figcaption>Robert Wright, <i>Nonzero: The Logic of Human Destiny</i>.</figcaption></figure>
      <figure class="figlayer" data-vis="img-cooperation"><img src="{IMG}/image21.png" alt="Middle powers cooperating on shared infrastructure and standards"/><figcaption>Data Mining 1 by Hanna Barakat &amp; Archival Images of AI + AIxDESIGN · <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noopener">CC-BY 4.0</a></figcaption></figure>

      <figure class="figlayer" data-vis="hcards-goals"><div class="hcards-stage-hint"><i class="fa-regular fa-arrow-left"></i> Scroll the goal cards horizontally <i class="fa-regular fa-arrow-right"></i></div></figure>
      <figure class="figlayer" data-vis="art-levers"><img src="{IMG}/image35.png" alt="Joining the Table by Yutong Liu — Better Images of AI"/><figcaption><a href="https://betterimagesofai.org" target="_blank" rel="noopener">Joining the Table by Yutong Liu — Better Images of AI</a> · <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noopener">CC-BY 4.0</a></figcaption></figure>
      <figure class="figlayer" data-vis="art-scoreboard"><div class="artbox"></div></figure>

      <figure class="figlayer" data-vis="chart-gemini">
        <div class="chartwrap" style="text-align:center"><div class="chart-brand" style="justify-content:center"><img src="https://www.google.com/s2/favicons?domain=deepmind.google&amp;sz=32" width="22" height="22" alt=""/><span>Gemini 3.5 Flash benchmarks · <a href="https://deepmind.google/models/gemini/flash/" target="_blank" rel="noopener">Google</a></span></div>
        <select class="gemsel" id="gemSel"></select>
        <div class="gem-cat" id="gemCat"></div>
        <svg class="csvg" id="gemChart" viewBox="0 0 600 320" role="img" aria-label="Gemini benchmark by model"></svg></div>
      </figure>

      <figure class="figlayer" data-vis="chart-glm">
        <div class="chartwrap" style="text-align:center"><div class="chart-brand" style="justify-content:center"><img src="https://www.google.com/s2/favicons?domain=z.ai&amp;sz=32" width="22" height="22" alt=""/><span>GLM 5.2 benchmarks · <a href="https://docs.z.ai/guides/llm/glm-5.2" target="_blank" rel="noopener">Z.ai</a></span></div>
        <select class="gemsel" id="glmSel"></select>
        <div class="gem-cat" id="glmCat"></div>
        <svg class="csvg" id="glmChart" viewBox="0 0 600 320" role="img" aria-label="GLM benchmark by model"></svg></div>
      </figure>

      <figure class="figlayer" data-vis="img-bench"><img src="{IMG}/image22.png" alt="Benchmark opportunity for middle powers — agriculture and local productivity"/></figure>

      <figure class="figlayer" data-vis="img-dataset-trio">
        <div class="dataset-trio">
          <figure class="dataset-trio-item"><img src="{IMG}/image2.png" alt="Biased Algorithms Learn From Biased Data"/><figcaption><a href="https://www.forbes.com/sites/cognitiveworld/2020/02/07/biased-algorithms/" target="_blank" rel="noopener">Biased Algorithms Learn From Biased Data</a> · Forbes</figcaption></figure>
          <figure class="dataset-trio-item"><img src="{IMG}/image20.jpg" alt="Soaps in London = Soap in Nepal"/><figcaption><a href="https://arxiv.org/abs/1906.02659" target="_blank" rel="noopener">Does Object Recognition Work The Same Way for Everyone?</a></figcaption></figure>
          <figure class="dataset-trio-item"><img src="{IMG}/image10.png" alt="Casteist depictions produced by OpenAI"/><figcaption><a href="https://www.technologyreview.com/2025/10/01/1124621/openai-india-caste-bias/" target="_blank" rel="noopener">Casteist depictions produced by OpenAI</a> · MIT Technology Review</figcaption></figure>
        </div>
      </figure>
      <figure class="figlayer" data-vis="art-axes"><img src="{IMG}/image34.png" alt="Language axis — figure at a typewriter, red script flowing from the keys"/></figure>
      <figure class="figlayer" data-vis="img-culture7">
        <div class="culture-stack">
          <img src="{IMG}/image26.png" alt="Van Gogh landscape vs Kamala Harris in the style of Van Gogh (DALL·E 3)"/>
          <img src="{IMG}/image27.png" alt="Madhubani painting vs Kamala Harris in the style of a Madhubani painting"/>
        </div>
      </figure>
      <figure class="figlayer" data-vis="img-axis-domain"><img src="{IMG}/image33.png" alt="What AI measures vs what the majority world needs — domain understanding gap"/></figure>
      <figure class="figlayer" data-vis="img-kin"><img src="{IMG}/image15.png" alt="Gooey.AI low-resource language eval for Hausa"/><figcaption>Our low-resource-language eval for Hausa — <a href="https://gooey.ai/language" target="_blank" rel="noopener">gooey.ai/language</a> · Gooey.AI, ClearGlobal &amp; the Gates Foundation.</figcaption></figure>
      <figure class="figlayer" data-vis="img-culture8"><img src="{IMG}/image36.gif" alt="Indian miniature-style painting — two women in traditional dress riding a motorcycle past a street scene"/><figcaption>Dataset → fine-tuned image model → custom video — <a href="https://gooey.ai/beyondbias" target="_blank" rel="noopener">gooey.ai/beyondbias</a></figcaption></figure>

      <figure class="figlayer" data-vis="art-lockin"><img src="{IMG}/image29.png" alt="Jensen Huang presenting NVIDIA Blackwell GPU architecture"/><figcaption>Jensen Huang's calls for nations to build their own sovereign data centers</figcaption></figure>
      <figure class="figlayer" data-vis="art-actors"><img src="{IMG}/image39.png" alt="How Nvidia and OpenAI fuel the AI money machine — network diagram of investments and hardware flows"/><figcaption>How Nvidia and OpenAI Fuel the AI Money Machine · Source: Bloomberg News reporting</figcaption></figure>
      <figure class="figlayer" data-vis="hcards-recs"><div class="hcards-stage-hint"><i class="fa-regular fa-arrow-left"></i> Scroll the recommendation cards horizontally <i class="fa-regular fa-arrow-right"></i></div></figure>

      <figure class="figlayer" data-vis="art-edge">
        <div class="culture-stack">
          <figure class="culture-stack-item">
            <img src="{IMG}/image37.png" alt="Continued Opportunity by Suraj Rai — Better Images of AI"/>
            <figcaption><a href="https://betterimagesofai.org" target="_blank" rel="noopener">Continued Opportunity by Suraj Rai &amp; Digit - Better Images of AI</a> · <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noopener">CC-BY 4.0</a></figcaption>
          </figure>
          <figure class="culture-stack-item">
            <img src="{IMG}/image38.png" alt="Continued Mining by Suraj Rai — Better Images of AI"/>
            <figcaption><a href="https://betterimagesofai.org" target="_blank" rel="noopener">Continued Mining by Suraj Rai &amp; Digit by Better Images of AI</a> · <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noopener">CC-BY 4.0</a></figcaption>
          </figure>
        </div>
      </figure>
      <figure class="figlayer" data-vis="img-hotswap">
        <div class="culture-stack">
          <img src="{IMG}/image31.png" alt="Today: App talks to OpenAI APIs"/>
          <img src="{IMG}/image32.png" alt="With AI standards: App talks via AI Standard APIs to private and open source providers"/>
        </div>
      </figure>
      <figure class="figlayer" data-vis="img-landscape"><img src="{IMG}/image3.png" alt="The Agriculture AI Landscape (Figure 8)"/><figcaption><b>Figure 8.</b> An Overview of the Agriculture AI landscape.</figcaption></figure>
      <figure class="figlayer" data-vis="img-dg"><img src="{IMG}/image23.png" alt="Digital Green impact: 17% income increase; 4.1M farmers reached"/><figcaption>Digital Green's impact: +17% farmer income, cost down from $35→$3.50, 4.1M farmers reached (70% women).</figcaption></figure>
      <figure class="figlayer" data-vis="img-chat"><img src="{IMG}/image7.png" alt="Farmer.CHAT WhatsApp exchange"/><figcaption>A real Farmer.CHAT exchange — grounded, cited advice by text or voice, in the user's language.</figcaption></figure>

      <figure class="figlayer" data-vis="art-conclusion">
        <div class="lever-grid" aria-label="Four levers for AI sovereignty">
          <article class="lg-card"><i class="fa-regular fa-ruler"></i><h5>Benchmarks</h5><p>that define what good AI means for their country.</p></article>
          <article class="lg-card"><i class="fa-regular fa-database"></i><h5>Datasets</h5><p>that make underrepresented communities visible and drive the next wave of productivity for everyone.</p></article>
          <article class="lg-card"><i class="fa-regular fa-microchip"></i><h5>Deployable models</h5><p>that reduce dependency on any one vendor or country.</p></article>
          <article class="lg-card"><i class="fa-regular fa-diagram-project"></i><h5>Open markets &amp; workflows</h5><p>that let useful AI spread across sectors and borders.</p></article>
        </div>
      </figure>
"""

EXTRA_CSS = """
/* horizontal cards */
.step-hscroll{min-height:100vh}
.hscroll-track{display:flex;gap:20px;overflow-x:auto;scroll-snap-type:x mandatory;scroll-behavior:smooth;-webkit-overflow-scrolling:touch;padding:8px 0 24px;margin-top:12px}
.hscroll-track:focus{outline:2px solid var(--gy-orange);outline-offset:4px}
.hcard{flex:0 0 min(420px,88vw);scroll-snap-align:start;display:flex;flex-direction:column;background:var(--gy-surface-50);border:1px solid var(--gy-line-soft);border-radius:16px;overflow:hidden;min-height:min(72vh,640px)}
.hcard img{width:100%;aspect-ratio:16/10;object-fit:cover;border-bottom:1px solid var(--gy-line-soft);max-height:42vh}
.hcard h3{font-family:var(--gy-font-serif);font-weight:400;font-size:22px;line-height:1.2;margin:18px 20px 10px}
.hcard p{font-size:15.5px;line-height:1.58;color:var(--gy-ink-muted);margin:0 20px 22px;flex:1}
.hcards-stage-hint{font-size:13px;color:var(--gy-ink-soft);text-align:center;padding:20px}
.hcards-stage-hint i{margin:0 6px}

/* chart brand row */
.chart-brand{display:flex;align-items:center;gap:10px;font-family:var(--gy-font-serif);font-size:17px;margin:0 0 8px}
.chart-brand img{border-radius:4px}
.chart-brand a{color:var(--gy-ink-muted)}

.scrolly-finale{display:block;max-width:none;padding:0 clamp(24px,6vw,96px)}
.scrolly-finale .col-text{max-width:640px;margin:0 auto;text-align:center}
.scrolly-finale .step{align-items:center;text-align:center}
.scrolly-finale .step-eyebrow{justify-content:center}
"""

EXTRA_JS = """
const GLM_COLS=[{k:'glm52',label:'GLM 5.2',hl:true},{k:'glm5',label:'GLM 5'},{k:'g35f',label:'Gemini 3.5 Flash'},{k:'gpt55',label:'GPT-5.5'},{k:'cs46',label:'Claude Sonnet 4.6'},{k:'qwen3',label:'Qwen3'}];
const GLM=[
 {cat:'Coding',bench:'SWE-Bench Pro',unit:'%',v:{glm52:58.2,glm5:52.1,g35f:55.1,gpt55:58.6,cs46:null,qwen3:51.4}},
 {cat:'Coding',bench:'Terminal-Bench 2.1',unit:'%',v:{glm52:71.4,glm5:65.8,g35f:76.2,gpt55:78.2,cs46:69.5,qwen3:68.1}},
 {cat:'Reasoning',bench:"Humanity's Last Exam",unit:'%',v:{glm52:38.6,glm5:34.2,g35f:40.2,gpt55:41.4,cs46:33.2,qwen3:36.8}},
 {cat:'Reasoning',bench:'ARC-AGI-2',unit:'%',v:{glm52:68.4,glm5:61.2,g35f:72.1,gpt55:84.6,cs46:58.3,qwen3:64.7}},
 {cat:'Agentic',bench:'MCP Atlas',unit:'%',v:{glm52:79.2,glm5:72.5,g35f:83.6,gpt55:75.3,cs46:69.5,qwen3:74.8}},
 {cat:'Multimodal',bench:'MMMU-Pro',unit:'%',v:{glm52:78.1,glm5:74.3,g35f:83.6,gpt55:81.2,cs46:74.5,qwen3:76.9}},
 {cat:'Expert',bench:'Finance Agent v2',unit:'%',v:{glm52:54.2,glm5:48.6,g35f:57.9,gpt55:51.8,cs46:51.0,qwen3:49.3}},
 {cat:'Long context',bench:'MRCR v2 (8-needle)',unit:'%',v:{glm52:74.8,glm5:69.1,g35f:77.3,gpt55:94.8,cs46:84.9,qwen3:71.2}}];
let glmIdx=0;
function renderGlmControls(){
 const sel=document.getElementById('glmSel');if(!sel)return;
 sel.innerHTML=GLM.map((r,i)=>`<option value="${i}" ${i===glmIdx?'selected':''}>${r.cat} — ${r.bench}</option>`).join('');
 sel.onchange=()=>{glmIdx=+sel.value;renderGlm();};renderGlm();
}
function renderGlm(){
 const row=GLM[glmIdx];const catEl=document.getElementById('glmCat');if(!row||!catEl)return;
 catEl.textContent=row.cat;
 const svg=document.getElementById('glmChart');const W=600,H=320,m={l:150,r:54,t:8,b:8};
 const vals=GLM_COLS.map(c=>row.v[c.k]).filter(v=>v!=null);const max=row.unit==='elo'?Math.max(...vals)*1.1:100;const bh=(H-m.t-m.b)/GLM_COLS.length;
 let s='';GLM_COLS.forEach((c,i)=>{const v=row.v[c.k];const y=m.t+i*bh+bh*0.2;const w=v==null?0:(v/max)*(W-m.l-m.r);
  s+=`<text x="${m.l-8}" y="${y+bh*0.4}" text-anchor="end" style="font-size:11.5px;fill:var(--gy-ink);font-weight:${c.hl?700:400}">${c.label}</text>`;
  if(v==null){s+=`<text x="${m.l+6}" y="${y+bh*0.42}" style="font-size:11px;fill:var(--gy-ink-soft)">not reported</text>`;}
  else{s+=`<rect x="${m.l}" y="${y}" width="${w}" height="${bh*0.52}" rx="3" fill="${c.hl?PALETTE.orange:PALETTE.purple}" fill-opacity="${c.hl?0.95:0.8}"/><text x="${m.l+w+6}" y="${y+bh*0.42}" style="font-size:11.5px;font-weight:700;fill:var(--gy-ink)">${row.unit==='elo'?v:v+'%'}</text>`;}});
 svg.innerHTML=s;
}

function initHScrollTracks(){
 document.querySelectorAll('.hscroll-track').forEach(track=>{
  track.addEventListener('wheel',e=>{
   if(Math.abs(e.deltaY)>Math.abs(e.deltaX)){e.preventDefault();track.scrollLeft+=e.deltaY;}
  },{passive:false});
 });
}
"""

def patch_html(text: str) -> str:
    import re

    # CSS before mobile inline-vis
    text = text.replace(
        "/* mobile inline visual (clone target) */",
        EXTRA_CSS + "\n/* mobile inline visual (clone target) */",
    )

    # Replace figlayers block
    text = re.sub(
        r'<figure class="figlayer" data-vis="art-abstract">.*?</figure>\s*<figure class="figlayer" data-vis="art-conclusion">.*?</figure>',
        FIGLAYERS.strip(),
        text,
        count=1,
        flags=re.S,
    )

    # Replace col-text
    text = re.sub(
        r'<div class="col-text">.*?</div>\s*\n</div>\s*\n<!-- ===================== FOOTER',
        COL_TEXT.strip() + "\n</div>\n\n<!-- ===================== FOOTER",
        text,
        count=1,
        flags=re.S,
    )

    # Remove chart-claude references in injectArt if any - art still works

    # Insert GLM JS before art injection
    text = text.replace(
        "/* ---------- art injection ---------- */",
        EXTRA_JS + "\n/* ---------- art injection ---------- */",
    )

    # Update globe flight
    old_globe = """ function updateGlobeFlight(){
  if(!globeCtrl||!globeCtrl.isReady())return;
  const currentVis=window.sovereignCurrentVis||'art-abstract';
  const scrollY=window.scrollY;
  const tStart=1;
  const tEnd=layout.tEnd;

  if(scrollY<tStart){
   globeCtrl.setVisible(true);
   globeCtrl.setLayout(heroGlobeRect());
   return;
  }

  if(currentVis!=='art-abstract'){
   globeCtrl.setVisible(false);
   return;
  }

  globeCtrl.setVisible(true);
  const t=Math.max(0,Math.min(1,(scrollY-tStart)/(tEnd-tStart)));

  if(t>=1){
   globeCtrl.setLayout(layout.to);
   return;
  }

  globeCtrl.setLayout(lerpRect(layout.from,layout.to,t));
 }"""

    new_globe = """ function updateGlobeFlight(){
  if(!globeCtrl||!globeCtrl.isReady())return;
  const currentVis=window.sovereignCurrentVis||'art-abstract';

  if(GLOBE_SCROLL_VIS.has(currentVis)){
   globeCtrl.setVisible(true);
   globeCtrl.setLayout(heroGlobeRect());
   return;
  }

  globeCtrl.setVisible(false);
 }"""
    text = text.replace(old_globe, new_globe)

    # DOMContentLoaded - add glm + hscroll
    text = text.replace(
        "renderDC();renderPub();renderClaude();renderGemControls();",
        "renderDC();renderPub();renderGemControls();renderGlmControls();",
    )
    text = text.replace(
        "injectArt();initScrolly(globeCtrl,updateGlobeFlight);initChrome();",
        "injectArt();initScrolly(globeCtrl,updateGlobeFlight);initHScrollTracks();initChrome();",
    )

    # injectArt skip list
    text = text.replace(
        "if(name==='art-abstract')return;",
        "if(name==='art-abstract'||name==='hcards-goals'||name==='hcards-recs')return;",
    )

    # Hero dek typo fix
    text = text.replace(
        "What AI sovereignty means — and how we can achieve it, together.",
        "What AI sovereignty means and how we can achieve it.",
    )

    if "scrolly-finale" not in text:
        text = text.replace(
            "<!-- ===================== FOOTER ===================== -->",
            SCROLLY_FINALE.strip() + "\n<!-- ===================== FOOTER ===================== -->",
            1,
        )

    return text


def main():
    text = HTML.read_text()
    HTML.write_text(patch_html(text))
    print(f"Updated {HTML}")


if __name__ == "__main__":
    main()
