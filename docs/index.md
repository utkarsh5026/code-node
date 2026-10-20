---
hide:
  - navigation
  - toc
---

# code-node

Point it at a Python project and it draws what one function does when it runs: the functions it calls, and the AWS
services, HTTP endpoints and environment variables those reach. It reads the source with `ast`, so nothing is
imported or run.
{ .cn-lede }

```bash
pip install code-node-graph
code-node path/to/your/repo
```

<figure class="cn-trace">
<div class="cn-trace-body">
<div class="cn-code" aria-label="lambda_handler in orders/handler.py">
<div class="cn-file">orders/handler.py</div>
<span class="cn-line" tabindex="0" data-on="event>handler"><i>30</i>def lambda_handler(event, context):</span>
<span class="cn-line"><i>31</i>    saved = 0</span>
<span class="cn-line" tabindex="0" data-on="event>handler"><i>32</i>    for record in event["Records"]:</span>
<span class="cn-line"><i>33</i>        bucket = record["s3"]["bucket"]["name"]</span>
<span class="cn-line"><i>34</i>        key = record["s3"]["object"]["key"]</span>
<span class="cn-line" tabindex="0" data-on="handler>read read>s3"><i>35</i>        for order in read_orders(bucket, key):</span>
<span class="cn-line"><i>36</i>            if not check(order):</span>
<span class="cn-line"><i>37</i>                log.warning("skipping %s", order.get("id"))</span>
<span class="cn-line"><i>38</i>                continue</span>
<span class="cn-line" tabindex="0" data-on="handler>save save>ddb save>s3 env>save"><i>39</i>            store.save(order)</span>
<span class="cn-line" tabindex="0" data-on="handler>announce announce>sns announce>chat chat>web env>announce env>chat"><i>40</i>            announce(order)</span>
<span class="cn-line"><i>41</i>            saved += 1</span>
<span class="cn-line"><i>42</i>    return {"saved": saved}</span>
</div>
<div class="cn-graph-wrap">
--8<-- "graph-trace.svg"
</div>
</div>
<figcaption>The graph for <code>examples/orders-service</code> in this repository, starting from its Lambda handler.
Select a highlighted line to see the path it takes, or point at a box.</figcaption>
</figure>

## The page

The graph is one of two tabs on an HTML page. The other walks through each call step by step. It's one file that works
offline, and everything on it but opening a box's hidden calls works without JavaScript.

<figure class="cn-shot" markdown>
![A code-node page: the graph in its tab](images/page-light.webp#only-light){ loading=lazy }
![A code-node page: the graph in its tab](images/page-dark.webp#only-dark){ loading=lazy }
</figure>

## Running it

```console
$ code-node examples/orders-service --list
1 entry point in examples/orders-service:
   1. orders.handler.lambda_handler  a Lambda handler (event, context)  (orders/handler.py:30)
$ code-node examples/orders-service
orders.handler.lambda_handler: 8 functions, 4 AWS calls
```

With no arguments it looks for places your code starts: console scripts, Lambda handlers, FastAPI, Flask and Django routes,
Typer commands and `if __name__ == "__main__":` blocks. If it finds more than one, it asks. `code-node --serve` keeps
the page open and redraws it each time you save a file.

[Start](usage.md) has every option. [Read the map](reading.md) explains the boxes and colours.

## What it won't do

It never imports your modules, runs them, or calls AWS, and nothing leaves your machine. To name AWS operations, it
reads botocore's service files from disk.

Some calls can't be known without running the code, like a function picked out of a dict or a client a library hands
back. Those are left off the graph, and the page says where it stopped following.
