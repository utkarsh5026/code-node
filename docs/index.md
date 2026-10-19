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

## Every AWS call, with the permission it needs

The same example, as the page lists it. The page also writes these up as a starter IAM policy.

| Call | Permission | Where |
| --- | --- | --- |
| S3 GetObject | `s3:GetObject` | `orders/handler.py` line 21 |
| DynamoDB PutItem | `dynamodb:PutItem` | `orders/store.py` line 18 |
| S3 PutObject | `s3:PutObject` | `orders/store.py` line 23 |
| SNS Publish | `sns:Publish` | `orders/notify.py` line 16 |

Environment variables get the same treatment: `ORDERS_TABLE`, `ARCHIVE_BUCKET` and `ORDERS_TOPIC` must be set, and
`CHAT_WEBHOOK` falls back to a default.

## Problems it points out

For this example it found three:

- `requests.post` in `notify.py` has no timeout. If the chat server doesn't answer, the call waits as long as the
  connection stays open.
- `put_item` runs once per order. `table.batch_writer()` would send up to 25 at a time.
- `sns.publish` runs once per order. `publish_batch` would send up to 10 at a time.

It also catches list calls that only read the first page, `except: pass`, and secrets written into the code.
[All of them](reading.md#findings).

## The page

Everything above is on one HTML page, along with the findings and each call step by step. It works offline, and it has
no JavaScript.

<figure class="cn-shot" markdown>
![A code-node page: cards, findings and the graph](images/page-light.webp#only-light){ loading=lazy }
![A code-node page: cards, findings and the graph](images/page-dark.webp#only-dark){ loading=lazy }
</figure>

## Running it

```console
$ code-node examples/orders-service --list
1 entry point in examples/orders-service:
   1. orders.handler.lambda_handler  a Lambda handler (event, context)  (orders/handler.py:30)
$ code-node examples/orders-service
orders.handler.lambda_handler: 8 functions, 4 AWS calls
```

With no arguments it looks for places your code starts: console scripts, Lambda handlers, FastAPI and Flask routes,
Typer commands and `if __name__ == "__main__":` blocks. If it finds more than one, it asks. `code-node --serve` keeps
the page open and redraws it each time you save a file.

[Start](usage.md) has every option. [Read the map](reading.md) explains the boxes and colours.

## What it won't do

It never imports your modules, runs them, or calls AWS, and nothing leaves your machine. To name AWS operations and
their permissions, it reads botocore's service files from disk.

Some calls can't be known without running the code, like a function picked out of a dict or a client a library hands
back. Those are left off the graph, and the page says where it stopped following.
