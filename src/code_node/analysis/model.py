"""
The dataclasses a CodeMap is made of: the steps of the outline, the AWS calls, the
environment and event it reads, its functions and imports, and the lines findings
point at.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from .aws_model import _event_label, _service_name


@dataclass
class CodeStep:
    """
    A line of how_it_works()'s outline: a statement of the function's own code that does something worth knowing
    (calls AWS, the network or one of its own functions, reads the event or an environment variable, logs, returns or
    raises), or a loop, branch, `with` or `try` around such lines, with what it does in plain English.
    """

    file: str
    line: int
    code: str  # the statement on one line: "for record in event['Records']:"
    kind: str = "do"  # 'do', 'loop', 'if', 'else', 'with', 'try', 'except', 'return', 'raise', 'def', 'module'
    notes: list[tuple[str, str]] = field(default_factory=list)  # (kind, what): ('aws-reads', 'S3 GetObject'), ...
    steps: list[CodeStep] = field(default_factory=list)  # the lines under it: a loop's body, a function's steps
    calls: list[CodeStep] = field(default_factory=list)  # 'def' steps: its own functions this line calls
    name: str = ""  # a 'def' step: the function ('db.connect'); a 'module' step: the module ('db')
    seen: bool = False  # a 'def' step whose steps are shown where it was first called, not again here
    holds: list[tuple[str, str]] = field(default_factory=list)  # the names it sets and what they hold, in words:
    # [('bucket', 'event Records[].s3.bucket.name'), ('self.table', 'a DynamoDB Table')]
    given: list[tuple[str, str]] = field(default_factory=list)  # what goes into its AWS calls, by call and argument:
    # [('S3 PutObject Bucket', 'env ARCHIVE_BUCKET')]
    when: list[str] = field(default_factory=list)  # a 'def' step: the tests of the ifs around the line calling it,
    # outermost first: ['args.command == "init"'], ['check(order)'] after `if not check(order): continue`

    def walk(self) -> Iterable[CodeStep]:
        """
        This step and every step under it, in the order they're shown.
        """
        yield self
        for step in [*self.calls, *self.steps]:
            yield from step.walk()


@dataclass
class AwsCall:
    """
    An AWS API call the code makes, found by following its boto3 clients and resources.
    """

    service: str  # boto3's name: 's3', 'dynamodb'
    operation: str  # 'GetObject'
    access: str  # 'reads', 'writes', 'sends' (a message or event), 'runs' (invokes or starts something) or 'signs'
    # (a presigned link: no request)
    permission: str  # the IAM action its role needs: 's3:GetObject' ('' when it needs none)
    file: str
    line: int
    function: str  # where: 'etl.handler', or the module ('etl') for code that runs when it's imported
    code: str  # the call: "s3.get_object(Bucket=body['bucket'], Key=body['key'])"
    loop: str = ""  # the loop it's in: 'for row in rows:'
    pages: str = ""  # a list call: 'all' (a paginator, or it follows the next-page token), 'one' (its first page only)
    guessed: bool = False  # from the method's name alone: its client couldn't be followed
    startup: bool = False  # made when the code is imported (on Lambda, once per cold start), not on each call
    args: list[tuple[str, str]] = field(default_factory=list)  # where its arguments come from, the ones that can be
    # told: [('Bucket', 'env ARCHIVE_BUCKET'), ('Key', "'orders.json'")]

    @property
    def label(self) -> str:
        """
        'S3 GetObject'.
        """
        return f"{_service_name(self.service)} {self.operation}"


@dataclass
class LibraryCall:
    """
    A call through a library a library plugin knows (code_node.libraries): a Redis GET, a SQL INSERT, an OpenAI
    chat completion. Drawn as a box for its service, like an AWS service's.
    """

    library: str  # the plugin's name: 'redis', 'sql'
    service: str  # what it reaches, as people name it: 'Redis', 'PostgreSQL', 'OpenAI'
    operation: str  # 'GET', 'INSERT', 'chat.completions.create'
    access: str  # 'reads', 'writes', 'sends' or 'runs', as for AWS calls
    file: str
    line: int
    function: str  # where: 'cart.app.handler', or the module for code that runs when it's imported
    code: str  # the call: "r.get(f'cart:{user}')"
    target: str = ""  # what on: a key, a table, a collection, a model: 'cart:{user}', 'orders', 'gpt-4o'
    icon: str = ""  # its box's icon: 'database', 'queue', 'key', 'send', 'spark', 'bucket', 'cloud'
    loop: str = ""  # the loop it's in: 'for item in items:'
    startup: bool = False  # made when the code is imported
    flag: str = ""  # a warning about this call, in a few words: 'SQL built from the event'
    why: str = ""  # ...and as a sentence, for the findings
    batch: str = ""  # in a loop: the call that does many at once ('executemany()', 'a pipeline()')

    @property
    def label(self) -> str:
        """
        'Redis GET', 'PostgreSQL INSERT'.
        """
        return f"{self.service} {self.operation}"

    @property
    def row(self) -> str:
        """
        How its box lists it: 'GET cart:{user}', 'INSERT orders'.
        """
        return f"{self.operation} {self.target}".strip()


@dataclass
class Deployment:
    """
    What a deploy file says about where an entry point runs, read by a deploy plugin (code_node.deploys): a Lambda
    function in a SAM template or serverless.yml, with its settings and what its role may call. Its platform's
    checks run against it: variables that aren't set, AWS calls its role doesn't allow, the Python it runs on.
    """

    name: str  # the function's name in the file: 'CartFunction', 'checkout'
    source: str  # the file that says so: 'template.yaml'
    reader: str  # the deploy plugin that read it: 'sam'
    file: str  # the Python file of its entry point: 'cart/app.py'
    function: str  # the entry point's function in that file: 'on_checkout'
    platform: str = "lambda"  # where it runs, a code_node.platforms name
    line: int = 0  # where the file says so
    runtime: str | None = None  # 'python3.12'
    timeout: int | None = None  # seconds
    memory: int | None = None  # MB
    env_names: set[str] = field(default_factory=set)  # the environment variables it's given (names only)
    env_error: str | None = None  # why its variables can't be known, when they can't (env_names is then partial)
    layers: list[str] = field(default_factory=list)  # 'arn:aws:lambda:...:layer:pandas:3', 'DepsLayer'
    permissions: set[str] | None = None  # the IAM actions its role allows ('s3:GetObject', 'dynamodb:*'); None when
    # the file can't tell (a role made elsewhere, a policy it doesn't know)
    policies: list[str] = field(default_factory=list)  # what gives them, as the file says: 'DynamoDBReadPolicy'


@dataclass
class EnvRead:
    """
    An environment variable the code reads. Its value is never read: only its name.
    """

    name: str
    file: str
    line: int
    function: str
    required: bool  # os.environ['X']: a KeyError when it isn't set; os.environ.get / os.getenv give a default
    default: str = ""  # the default, as code
    startup: bool = False  # read when the code is imported


@dataclass
class EventField:
    """
    A field the code reads from its input: what its platform passes the entry point (a Lambda handler's event).
    """

    path: tuple[str, ...]  # ('Records', '[]', 'body', '{json}', 'bucket')
    file: str
    line: int
    required: bool  # event['x'] (a KeyError when it's missing), not event.get('x')

    @property
    def label(self) -> str:
        """
        'Records[].body (JSON) bucket'.
        """
        return _event_label(self.path)


@dataclass
class Commit:
    """
    A commit, as git blame tells it.
    """

    sha: str
    author: str
    time: int  # when it was made, in seconds since 1970
    subject: str  # its message's first line
    url: str = ""  # its page on the repository's host, when that's GitHub or GitLab

    @property
    def short(self) -> str:
        return self.sha[:7]


@dataclass
class History:
    """
    What git says about a function's lines as they are now: the commit that last changed one of them, how many commits
    and people they come from, and how many have changed since the last commit. Read by history.py; None on a
    function when the folder isn't in git.
    """

    last: Commit | None  # the newest commit among its lines; None when none of them is committed yet
    commits: int  # the commits its lines come from
    authors: list[str]  # who wrote them, most lines first
    first: int  # when the oldest of them was made (about when the function was written), in seconds since 1970
    uncommitted: int  # its lines changed since the last commit
    now: int  # when this was read, for 'three days ago'

    def ago(self, time: int) -> str:
        """
        'today', '3 days ago', '2 months ago', '1 year ago'.
        """
        days = max(0, self.now - time) // 86_400
        for size, unit in ((365, "year"), (30, "month"), (7, "week"), (1, "day")):
            if days >= size:
                count = days // size
                return f"{count} {unit}{'' if count == 1 else 's'} ago"
        return "today"


@dataclass
class CodeFunction:
    """
    One of the code's own functions that runs when the entry point does.
    """

    name: str  # 'db.connect', 'repo.Orders.save'
    file: str
    line: int
    lines: int
    args: str  # 'host, password'
    doc: str = ""  # its docstring's first line
    called_from: list[str] = field(default_factory=list)  # 'etl.handler line 19'
    when: dict[str, str] = field(default_factory=dict)  # a place in called_from -> the test it's called under: the if
    # nearest around the call, else the nearest `if x: return` above it ('args.serve', not every check before it)
    depth: int = 0  # calls from the entry point (the entry point is 0)
    is_async: bool = False  # async def: a call that blocks in it holds up everything else on its event loop
    history: History | None = None  # what git says about its lines, when the folder is in git (history.py)


@dataclass
class ImportUse:
    """
    A module the code imports, and where Python finds it.
    """

    module: str  # as written: 'requests', 'db', 'pkg.sub'
    source: str  # 'own' (its own files), 'stdlib', 'runtime' (boto3, botocore...), 'package' (a library packed in
    # it), 'layer' (none of those, and the function has layers), 'missing', or 'removed' (from the runtime's Python)
    file: str
    line: int
    optional: bool = False  # in a try that catches ImportError
    startup: bool = True  # imported when the module loads, not inside a function

    @property
    def top(self) -> str:
        return self.module.split(".")[0]


@dataclass
class CodeSpot:
    """
    A line how_it_works()'s findings are about.
    """

    kind: str  # 'http', 'sleep', 'write', 'secret', 'swallow', 'client', 'connect', 'command', 'syntax'
    file: str
    line: int
    function: str
    code: str
    detail: str = ""  # http: the method; write: the path; secret: its name (never the value); client: the service;
    # connect: the service a library's client is for ('Redis'); command: what goes into it from the input
    ok: bool = True  # http: has a timeout; client, connect: made once and reused; command: nothing from the input
    loop: str = ""
    startup: bool = False  # when the code is imported
    waits: str = ""  # connect: how long a call through it waits when the service doesn't answer, when that's too long
    # ('as long as Redis takes': no timeout); '' when it's given one
    fix: str = ""  # connect: how to give it a timeout: 'Redis(..., socket_timeout=5)'


@dataclass
class CodeMap:
    """
    How Python code works from one entry point, read with Python's ast module (nothing in it is run): what runs when
    it's imported, the steps of each call from the entry point on, following its own functions, and what they reach
    outside: AWS calls, environment variables, the fields of its input, libraries and HTTP.
    """

    function: Deployment | Any  # what the findings check against: where a deploy file says it runs (a Lambda function
    # in template.yaml), else None
    handler: str | None  # the entry point as given: 'etl.handler'
    platform: str = ""  # the platform it runs on, by name ('lambda'): its checks and wording. '' is plain Python
    handler_file: str | None = None  # 'etl.py'
    entry: str | None = None  # the function it starts from, as module.name ('etl.handler'); None when it isn't there
    entry_line: int = 0
    params: list[str] = field(default_factory=list)  # the entry point's parameters: 'event', 'ctx=…', '*args'
    is_async: bool = False  # async def: the Python runtime doesn't await it
    startup: list[CodeStep] = field(default_factory=list)  # what runs when the code is imported
    steps: list[CodeStep] = field(default_factory=list)  # one 'def' step: the entry point's, with every step under it
    functions: list[CodeFunction] = field(default_factory=list)  # its own functions the entry point reaches, in order
    aws: list[AwsCall] = field(default_factory=list)
    library_calls: list[LibraryCall] = field(default_factory=list)  # calls through the libraries plugins know
    env: list[EnvRead] = field(default_factory=list)
    event: list[EventField] = field(default_factory=list)
    imports: list[ImportUse] = field(default_factory=list)
    spots: list[CodeSpot] = field(default_factory=list)
    returns: list[tuple[str, str, int]] = field(
        default_factory=list
    )  # what the entry point returns: (code, file, line)
    routes: list[tuple[str, str, str]] = field(default_factory=list)  # web routes: (method, path, function)
    files: int = 0  # Python files read
    lines: int = 0  # their lines
    other_files: int = 0  # its own Python files the entry point's code never imports (tests, scripts, other handlers)
    unreached: int = 0  # functions in the files it read that the entry point never reaches
    skipped: list[tuple[str, str]] = field(default_factory=list)  # (file, why) for files that couldn't be read
    limited: str = ""  # what was cut short, when something was
    note: str | None = None  # why there's nothing to map: not Python, a container image, no entry point file
    handlers: list[str] = field(default_factory=list)  # when the entry point isn't in its file: the functions there
    # that could be (that take what its platform passes)
    plugins: list[str] = field(default_factory=list)  # the library plugins whose calls it found, by title: 'Redis'

    @property
    def services(self) -> list[str]:
        """
        The AWS services it calls, as people name them ('S3', 'DynamoDB'), in the order it first calls them.
        """
        return list(dict.fromkeys(_service_name(call.service) for call in self.aws))

    def to_df(self):
        """
        Its AWS calls, a row each.
        """
        import pandas as pd

        return pd.DataFrame([{**vars(call), "label": call.label} for call in self.aws])
