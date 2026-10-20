"""
Deploy files: what a project's own deploy configuration says about where each entry point runs. A deploy plugin
reads one kind of file (a SAM template, serverless.yml) and returns a Deployment for each function it declares: its
handler, the Python it runs on, its timeout and environment variables, and what its role may call. Pure, like
analysis/: the folder's reader hands it the files' text.

Deploy files stack with the rest: a handler they name is an entry point even when it isn't called handler(), and
its platform's checks then run against what the file says (an environment variable the code needs that isn't set,
an AWS call its role doesn't allow, a module that Python version removed).

Another package adds one by subclassing Deploy and naming it under the `code_node.deploys` entry point group:

    [project.entry-points."code_node.deploys"]
    cdk = "my_package.cdk:CdkApp"

or, from a script, with register_deploy(CdkApp()).
"""

from __future__ import annotations

import posixpath
import re
from fnmatch import fnmatchcase
from typing import Any, Iterable

from ..analysis.model import Deployment

ENTRY_POINT_GROUP = "code_node.deploys"

_BUILT_IN = ("code_node.deploys.sam:SamTemplate", "code_node.deploys.serverless:ServerlessFile")


class Deploy:
    """
    A kind of deploy file. A plugin sets `name`, `title` and `files` (the file names it reads, wherever they are in
    the folder), and overrides deployments(); grant() says how to allow what a function's role is missing.
    """

    name = ""  # 'sam'
    title = ""  # 'AWS SAM'
    files: tuple[str, ...] = ()  # 'template.yaml', 'template.yml'

    def deployments(self, files: dict[str, str], code: set[str]) -> list[Deployment]:
        """
        The functions its files declare, each with the Python file and function it starts from. files is {path: text}
        for the files named like its own; code is every Python file in the folder, to find handlers in.
        """
        return []

    def grant(self, deployment: Deployment, actions: list[str]) -> str:
        """
        How to give a function's role IAM actions it's missing, as an instruction: 'add dynamodb:PutItem to its
        role's policy'.
        """
        return f"allow {', '.join(actions)} in its role's policy in {deployment.source}"


_deploys: dict[str, Deploy] = {}

_loaded = False


def register_deploy(deploy: Deploy) -> None:
    """
    Adds a deploy plugin (or replaces the one with its name): its files are read from then on.
    """
    if not deploy.name or not deploy.files:
        raise ValueError("a deploy plugin needs a name and the files it reads")
    deploys()
    _deploys[deploy.name] = deploy


def _add(found: Deploy | type[Deploy]) -> None:
    deploy = found() if isinstance(found, type) else found
    if deploy.name and deploy.files:
        _deploys.setdefault(deploy.name, deploy)


def deploys() -> list[Deploy]:
    """
    Every deploy plugin: the built-in ones, then those installed packages add, loaded the first time it's asked.
    """
    global _loaded
    if not _loaded:
        _loaded = True
        from importlib import import_module
        from importlib.metadata import entry_points

        for target in _BUILT_IN:
            module, _, attr = target.partition(":")
            _add(getattr(import_module(module), attr))
        for point in entry_points(group=ENTRY_POINT_GROUP):
            try:
                _add(point.load())
            except Exception:  # noqa: BLE001  a broken plugin leaves the others working
                continue
    return list(_deploys.values())


def get_deploy(name: str) -> Deploy | None:
    return next((deploy for deploy in deploys() if deploy.name == name), None)


def deploy_file_names() -> set[str]:
    """
    The file names any deploy plugin reads: what the folder's reader keeps besides .py files.
    """
    return {name for deploy in deploys() for name in deploy.files}


def all_deployments(files: dict[str, str], code: Iterable[str]) -> list[Deployment]:
    """
    Every function the folder's deploy files declare, from every deploy plugin. A file a plugin can't read is
    skipped: deploy files are a help, never a reason to fail.
    """
    code = set(code)
    found: list[Deployment] = []
    for deploy in deploys():
        mine = {path: text for path, text in files.items() if posixpath.basename(path) in deploy.files}
        if not mine:
            continue
        try:
            found += deploy.deployments(mine, code)
        except Exception:  # noqa: BLE001  a file it can't read
            continue
    return found


def find_deployment(files: dict[str, str], code: Iterable[str], file: str, function: str) -> Deployment | None:
    """
    The deployment that starts at function() in file, if a deploy file declares one.
    """
    return next((d for d in all_deployments(files, code) if d.file == file and d.function == function), None)


def allowed(action: str, permissions: Iterable[str]) -> bool:
    """
    Whether an IAM action is allowed by a set of actions, with their wildcards: 's3:GetObject' by 's3:Get*'.
    """
    action = action.lower()
    return any(fnmatchcase(action, granted.lower()) for granted in permissions)


def resolve_handler(base: str, code_dir: str, handler: str, code: set[str]) -> tuple[str, str] | None:
    """
    The Python file and function a handler setting names, from the deploy file's folder and the code's folder in
    it: ('', 'src/', 'cart.app.on_checkout') -> ('src/cart/app.py', 'on_checkout'). None when no file matches.
    """
    module, _, function = str(handler).rpartition(".")
    if not module or not function:
        return None
    stem = posixpath.normpath(posixpath.join(base, code_dir or ".", module.replace(".", "/")))
    for candidate in (f"{stem}.py", f"{stem}/__init__.py"):
        if candidate in code:
            return candidate, function
    return None


def line_of(text: str, key: str, indent: int | None = None) -> int:
    """
    The line a mapping key is on in a YAML file ('CartFunction' -> 14), 0 when it can't be found.
    """
    spaces = r"[ \t]*" if indent is None else " " * indent
    found = re.search(rf"^{spaces}['\"]?{re.escape(key)}['\"]?\s*:", text, re.M)
    return text.count("\n", 0, found.start()) + 1 if found else 0


def load_yaml(text: str) -> Any:
    """
    A YAML (or JSON) deploy file as plain data. CloudFormation's short tags (!Ref, !GetAtt, !Sub) are read as the
    long forms ({'Ref': ...}, {'Fn::GetAtt': ...}); serverless.yml's ${...} variables stay as text. None when
    PyYAML isn't installed or the file doesn't parse.
    """
    try:
        import yaml
    except ImportError:
        return None

    class Loader(yaml.SafeLoader):
        pass

    def tagged(loader: Any, suffix: str, node: Any) -> Any:
        if isinstance(node, yaml.ScalarNode):
            value: Any = loader.construct_scalar(node)
        elif isinstance(node, yaml.SequenceNode):
            value = loader.construct_sequence(node, deep=True)
        else:
            value = loader.construct_mapping(node, deep=True)
        if suffix == "Ref":
            return {"Ref": value}
        if suffix == "GetAtt" and isinstance(value, str):
            value = value.split(".", 1)
        return {f"Fn::{suffix}": value}

    Loader.add_multi_constructor("!", tagged)
    try:
        return yaml.load(text, Loader=Loader)  # noqa: S506  a SafeLoader, with CloudFormation's tags
    except yaml.YAMLError:
        return None


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return list(value) if isinstance(value, list) else [value]


def statement_actions(document: Any) -> set[str] | None:
    """
    The actions a policy document's statements allow: {'s3:GetObject', 'dynamodb:*'}. None when it can't be told:
    a Deny or NotAction (what's left can't be listed), or an action that isn't written out.
    """
    if isinstance(document, dict) and "Statement" in document:
        document = document["Statement"]
    actions: set[str] = set()
    for statement in as_list(document):
        if not isinstance(statement, dict) or "NotAction" in statement or statement.get("Effect") != "Allow":
            return None
        for action in as_list(statement.get("Action")):
            if not isinstance(action, str):
                return None
            actions.add(action)
    return actions


MANAGED_POLICIES: dict[str, set[str]] = {  # AWS managed policies -> the actions they allow, for the ones Lambda
    # functions are given most (a policy not here leaves what a role allows unknown)
    "AWSLambdaBasicExecutionRole": {"logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"},
    "AWSLambdaExecute": {"logs:*", "s3:GetObject", "s3:PutObject"},
    "AWSLambdaSQSQueueExecutionRole": {"sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes",
                                       "logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"},
    "AWSLambdaDynamoDBExecutionRole": {"dynamodb:DescribeStream", "dynamodb:GetRecords", "dynamodb:GetShardIterator",
                                       "dynamodb:ListStreams", "logs:CreateLogGroup", "logs:CreateLogStream",
                                       "logs:PutLogEvents"},
    "AWSLambdaKinesisExecutionRole": {"kinesis:DescribeStream", "kinesis:DescribeStreamSummary", "kinesis:GetRecords",
                                      "kinesis:GetShardIterator", "kinesis:ListShards", "kinesis:ListStreams",
                                      "kinesis:SubscribeToShard", "logs:CreateLogGroup", "logs:CreateLogStream",
                                      "logs:PutLogEvents"},
    "AWSLambdaVPCAccessExecutionRole": {"ec2:CreateNetworkInterface", "ec2:DescribeNetworkInterfaces",
                                        "ec2:DescribeSubnets", "ec2:DeleteNetworkInterface",
                                        "ec2:AssignPrivateIpAddresses", "ec2:UnassignPrivateIpAddresses",
                                        "logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"},
    "AWSXRayDaemonWriteAccess": {"xray:PutTraceSegments", "xray:PutTelemetryRecords", "xray:GetSamplingRules",
                                 "xray:GetSamplingTargets", "xray:GetSamplingStatisticSummaries"},
    "AmazonS3ReadOnlyAccess": {"s3:Get*", "s3:List*", "s3:Describe*", "s3-object-lambda:Get*",
                               "s3-object-lambda:List*"},
    "AmazonS3FullAccess": {"s3:*", "s3-object-lambda:*"},
    "AmazonDynamoDBReadOnlyAccess": {"dynamodb:BatchGetItem", "dynamodb:ConditionCheckItem", "dynamodb:Describe*",
                                     "dynamodb:GetItem", "dynamodb:List*", "dynamodb:PartiQLSelect", "dynamodb:Query",
                                     "dynamodb:Scan", "dynamodb:GetRecords", "dynamodb:GetShardIterator"},
    "AmazonDynamoDBFullAccess": {"dynamodb:*"},
    "AmazonSQSFullAccess": {"sqs:*"},
    "AmazonSNSFullAccess": {"sns:*"},
    "AmazonKinesisFullAccess": {"kinesis:*"},
    "AmazonEventBridgeFullAccess": {"events:*"},
    "AWSStepFunctionsFullAccess": {"states:*"},
    "SecretsManagerReadWrite": {"secretsmanager:*"},
    "AmazonSSMReadOnlyAccess": {"ssm:Describe*", "ssm:Get*", "ssm:List*"},
    "AmazonBedrockFullAccess": {"bedrock:*"},
    "AdministratorAccess": {"*"},
}


__all__ = ["ENTRY_POINT_GROUP", "MANAGED_POLICIES", "Deploy", "all_deployments", "allowed", "deploy_file_names",
           "deploys", "find_deployment", "get_deploy", "register_deploy"]
