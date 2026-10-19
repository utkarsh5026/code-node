---
title: See your code as a graph
hide:
  - navigation
  - toc
---

<div class="cn-hero" markdown>

<div class="cn-hero-copy" markdown>

<span class="cn-chip">◆ reads your code · never runs it</span>

<h1 class="cn-title">Your code is a graph.<br><span class="cn-grad">See it.</span></h1>

<p class="cn-lede">One command. A map of what calls what, and everything it touches.</p>

<div class="cn-install"><code>pip install code-node-graph</code><button class="cn-copy" data-copy="pip install code-node-graph" title="Copy">copy</button></div>

<div class="cn-buttons">
<a class="cn-btn cn-btn-main" href="usage.html">Map my repo →</a>
<a class="cn-btn" href="reading.html">How to read it</a>
</div>

</div>

<div class="cn-hero-graph cn-canvas">
--8<-- "graph-hero.svg"
<span class="cn-hint">↖ point at a box</span>
</div>

</div>

<section class="cn-section cn-reveal" markdown>

<p class="cn-kicker"><span>01</span> COMES IN</p>

## Point. Run. Look. { .cn-h }

<div class="cn-split" markdown>

<div class="cn-term" aria-label="A terminal running code-node">
<div class="cn-term-bar"><i></i><i></i><i></i><span>~/orders-service</span></div>
<pre><code><span class="t-cmd" data-type="code-node">$ </span>
<span class="t-out t-dim">  1. orders.handler.lambda_handler   a Lambda handler</span>
<span class="t-out t-dim">  2. orders.cli.main                 the orders command</span>
<span class="t-out">Start from which one? <b>1</b></span>
<span class="t-out t-ok">✓ 8 functions · 4 AWS calls · 1 warning</span>
<span class="t-out t-link">↗ opened in your browser</span></code></pre>
</div>

<div class="cn-steps" markdown>

<div class="cn-step"><b>Finds the start</b><span>CLIs, Lambda handlers, web apps, <code>main()</code>.</span></div>
<div class="cn-step"><b>Follows every call</b><span>Into your functions, classes and files.</span></div>
<div class="cn-step"><b>Draws the map</b><span>Opens it in your browser. Done.</span></div>

</div>

</div>

</section>

<section class="cn-section cn-reveal" markdown>

<p class="cn-kicker"><span>02</span> ENTRY → CALLS</p>

## Tap a line. Watch the path light up. { .cn-h }

<div class="cn-trace" markdown>

<div class="cn-code" role="list" aria-label="lambda_handler, line by line">
<span class="cn-line" data-on="event>handler" role="listitem"><i>30</i>def lambda_handler(event, context):</span>
<span class="cn-line" data-on="event>handler" role="listitem"><i>32</i>    for record in event["Records"]:</span>
<span class="cn-line" data-on="handler>read read>s3" role="listitem"><i>35</i>        orders = read_orders(bucket, key)</span>
<span class="cn-line" data-on="handler>save save>ddb save>s3 env>save" role="listitem"><i>40</i>            store.save(order)</span>
<span class="cn-line" data-on="handler>announce announce>sns announce>chat chat>web env>chat" role="listitem"><i>41</i>            announce(order)</span>
</div>

<div class="cn-trace-graph cn-canvas">
--8<-- "graph-trace.svg"
</div>

</div>

</section>

<section class="cn-section cn-reveal" markdown>

<p class="cn-kicker"><span>03</span> REACHES</p>

## Know what it touches. { .cn-h }

<div class="cn-reach">
<div class="cn-pill k-reads"><i></i><b>reads</b><span>S3 GetObject</span></div>
<div class="cn-pill k-writes"><i></i><b>writes</b><span>DynamoDB PutItem</span></div>
<div class="cn-pill k-sends"><i></i><b>sends</b><span>SNS Publish</span></div>
<div class="cn-pill k-http"><i></i><b>the web</b><span>POST chat webhook</span></div>
<div class="cn-pill k-env"><i></i><b>env vars</b><span>ORDERS_TABLE</span></div>
</div>

<p class="cn-sub">Every AWS call comes with the IAM permission it needs. You even get a starter policy.</p>

</section>

<section class="cn-section cn-reveal" markdown>

<p class="cn-kicker cn-kicker-warn"><span>!</span> WORTH A LOOK</p>

## It flags what'll bite you later. { .cn-h }

<div class="cn-flags">
<div class="cn-flag"><b>No timeout</b><span>That HTTP call can hang forever.</span></div>
<div class="cn-flag"><b>First page only</b><span>Your list call quietly skips the rest.</span></div>
<div class="cn-flag"><b>Swallowed errors</b><span><code>except: pass</code> hides failures.</span></div>
<div class="cn-flag"><b>Secrets in code</b><span>Anyone who reads it gets them.</span></div>
</div>

</section>

<section class="cn-section cn-reveal" markdown>

<p class="cn-kicker"><span>04</span> LIVE</p>

## Save the file. The map redraws. { .cn-h }

<div class="cn-live">
<div class="cn-live-code"><span class="cn-live-file">notify.py</span><code>def page_oncall(order):</code><code>    sqs.send_message(...)</code><span class="cn-live-save">⌘S</span></div>
<div class="cn-live-arrow"></div>
<div class="cn-live-page"><span class="cn-live-dot">● live</span><div class="cn-mini"><b>announce()</b></div><div class="cn-mini cn-mini-new"><b>page_oncall()</b></div><div class="cn-mini cn-mini-aws">SQS</div></div>
</div>

<p class="cn-sub"><code>code-node --serve</code> keeps the page open and redraws it on every save.</p>

</section>

<section class="cn-section cn-reveal" markdown>

<p class="cn-kicker"><span>05</span> THE REAL THING</p>

## This is what you get. { .cn-h }

<figure class="cn-shot" markdown>
![A real code-node page: cards, findings and the graph](images/page-light.webp#only-light){ loading=lazy }
![A real code-node page: cards, findings and the graph](images/page-dark.webp#only-dark){ loading=lazy }
</figure>

</section>

<section class="cn-section cn-reveal" markdown>

<div class="cn-never">
<div><b>No imports</b><span>Your code is read, not run.</span></div>
<div><b>No AWS calls</b><span>Not one request.</span></div>
<div><b>No upload</b><span>Everything stays on your machine.</span></div>
</div>

</section>

<div class="cn-cta cn-reveal" markdown>

## Map your repo in ten seconds.

<div class="cn-install cn-install-big"><code>pip install code-node-graph && code-node</code><button class="cn-copy" data-copy="pip install code-node-graph && code-node" title="Copy">copy</button></div>

</div>
