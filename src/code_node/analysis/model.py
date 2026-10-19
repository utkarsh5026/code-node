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

    @property
    def label(self) -> str:
        """
        'S3 GetObject'.
        """
        return f"{_service_name(self.service)} {self.operation}"


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
    depth: int = 0  # calls from the entry point (the entry point is 0)


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

    kind: str  # 'http', 'sleep', 'write', 'secret', 'swallow', 'client', 'command', 'syntax'
    file: str
    line: int
    function: str
    code: str
    detail: str = ""  # http: the method; write: the path; secret: its name (never the value); client: the service
    ok: bool = True  # http: has a timeout; client: made once and reused
    loop: str = ""
    startup: bool = False  # when the code is imported


@dataclass
class CodeMap:
    """
    How Python code works from one entry point, read with Python's ast module (nothing in it is run): what runs when
    it's imported, the steps of each call from the entry point on, following its own functions, and what they reach
    outside: AWS calls, environment variables, the fields of its input, libraries and HTTP.
    """

    function: Any  # what the findings check against (a Lambda function in aws-analyzer); None here
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
    env: list[EnvRead] = field(default_factory=list)
    event: list[EventField] = field(default_factory=list)
    imports: list[ImportUse] = field(default_factory=list)
    spots: list[CodeSpot] = field(default_factory=list)
    returns: list[tuple[str, str, int]] = field(default_factory=list)  # what the entry point returns: (code, file, line)
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
