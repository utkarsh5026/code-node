"""
The Serverless Framework's serverless.yml: each function on a Python runtime, with the provider's settings applied,
its environment variables (names only), and what its role's statements allow.
"""

from __future__ import annotations

import posixpath
from typing import Any

from ..analysis.model import Deployment
from . import MANAGED_POLICIES, Deploy, as_list, line_of, load_yaml, resolve_handler, statement_actions

_DEFAULT_TIMEOUT = 6  # seconds: the Serverless Framework's default

_DEFAULT_MEMORY = 1024


def _statements(provider: dict[str, Any]) -> tuple[Any, Any]:
    """
    The provider's role statements and managed policies, from v3's iam.role or v2's iamRoleStatements. ('string',
    None) when the role is one made elsewhere (an ARN or a name).
    """
    iam = provider.get("iam") or {}
    role = iam.get("role") if isinstance(iam, dict) else None
    if isinstance(role, str):
        return "elsewhere", None
    if isinstance(role, dict):
        return role.get("statements") or [], role.get("managedPolicies")
    return provider.get("iamRoleStatements") or [], provider.get("iamManagedPolicies")


class ServerlessFile(Deploy):
    """
    serverless.yml (or .yaml) with provider.name aws.
    """

    name = "serverless"
    title = "Serverless Framework"
    files = ("serverless.yml", "serverless.yaml")

    def deployments(self, files: dict[str, str], code: set[str]) -> list[Deployment]:
        found: list[Deployment] = []
        for path, text in files.items():
            data = load_yaml(text)
            if not isinstance(data, dict) or not isinstance(data.get("provider"), dict):
                continue
            provider = data["provider"]
            if provider.get("name", "aws") != "aws":
                continue
            functions = data.get("functions") or {}
            if isinstance(functions, list):  # an old file: a list of {name: function}
                functions = {k: v for item in functions if isinstance(item, dict) for k, v in item.items()}
            if not isinstance(functions, dict):
                continue
            statements, managed = _statements(provider)
            for name, function in functions.items():
                if not isinstance(function, dict) or "image" in function:
                    continue
                runtime = function.get("runtime", provider.get("runtime"))
                if isinstance(runtime, str) and not runtime.startswith("python"):
                    continue
                where = resolve_handler(posixpath.dirname(path), "", function.get("handler", ""), code)
                if where is None:
                    continue
                env_names, env_error = set(), None
                for source in (provider.get("environment"), function.get("environment")):
                    if isinstance(source, dict):
                        env_names |= {str(key) for key in source}
                    elif source is not None:
                        env_error = "its environment comes from a file or a variable"
                actions = None
                if statements != "elsewhere":
                    actions = statement_actions(as_list(statements) + as_list(function.get("iamRoleStatements")))
                    for policy in as_list(managed):
                        granted = (
                            MANAGED_POLICIES.get(str(policy).rsplit("/", 1)[-1]) if isinstance(policy, str) else None
                        )
                        actions = None if granted is None or actions is None else actions | granted
                    if actions is not None:
                        actions |= MANAGED_POLICIES["AWSLambdaBasicExecutionRole"]
                        for event in as_list(function.get("events")):
                            if isinstance(event, dict) and "sqs" in event:
                                actions |= MANAGED_POLICIES["AWSLambdaSQSQueueExecutionRole"]
                            if isinstance(event, dict) and "stream" in event:
                                actions |= (
                                    MANAGED_POLICIES["AWSLambdaDynamoDBExecutionRole"]
                                    | MANAGED_POLICIES["AWSLambdaKinesisExecutionRole"]
                                )
                timeout = function.get("timeout", provider.get("timeout", _DEFAULT_TIMEOUT))
                memory = function.get("memorySize", provider.get("memorySize", _DEFAULT_MEMORY))
                layers = [str(layer) for layer in as_list(function.get("layers", provider.get("layers")))]
                found.append(
                    Deployment(
                        str(name),
                        path,
                        self.name,
                        where[0],
                        where[1],
                        "lambda",
                        line_of(text, str(name), 2),
                        runtime if isinstance(runtime, str) else None,
                        timeout if isinstance(timeout, int) else None,
                        memory if isinstance(memory, int) else None,
                        env_names,
                        env_error,
                        layers,
                        actions,
                        ["provider.iam.role.statements"],
                    )
                )
        return found

    def grant(self, deployment: Deployment, actions: list[str]) -> str:
        return (
            f"add a statement that allows {', '.join(actions)} to provider.iam.role.statements in {deployment.source}"
        )
