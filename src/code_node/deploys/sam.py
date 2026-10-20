"""
AWS SAM and CloudFormation templates: each AWS::Serverless::Function (and AWS::Lambda::Function) on a Python
runtime, with Globals applied, its environment variables, and what its role allows: SAM's policy templates
(DynamoDBCrudPolicy), the managed policies it knows, inline statements, a role in the same template, and the
permissions its event sources add.
"""

from __future__ import annotations

import json
import posixpath
from typing import Any

from ..analysis.model import Deployment
from . import MANAGED_POLICIES, Deploy, allowed, as_list, line_of, load_yaml, resolve_handler, statement_actions

_D = "dynamodb:"

POLICY_TEMPLATES: dict[str, set[str]] = {  # SAM's policy templates -> the actions they allow
    "DynamoDBCrudPolicy": {_D + a for a in ("GetItem", "DeleteItem", "PutItem", "Scan", "Query", "UpdateItem",
                                            "BatchWriteItem", "BatchGetItem", "DescribeTable", "ConditionCheckItem")},
    "DynamoDBReadPolicy": {_D + a for a in ("GetItem", "Scan", "Query", "BatchGetItem", "DescribeTable")},
    "DynamoDBWritePolicy": {_D + a for a in ("PutItem", "UpdateItem", "BatchWriteItem")},
    "DynamoDBReconfigurePolicy": {_D + "DescribeTable", _D + "UpdateTable"},
    "DynamoDBStreamReadPolicy": {_D + a for a in ("DescribeStream", "GetRecords", "GetShardIterator", "ListStreams")},
    "S3ReadPolicy": {"s3:GetObject", "s3:ListBucket", "s3:GetBucketLocation", "s3:GetObjectVersion",
                     "s3:GetLifecycleConfiguration"},
    "S3WritePolicy": {"s3:PutObject", "s3:PutObjectAcl", "s3:PutLifecycleConfiguration"},
    "S3CrudPolicy": {"s3:GetObject", "s3:ListBucket", "s3:GetBucketLocation", "s3:GetObjectVersion", "s3:PutObject",
                     "s3:PutObjectAcl", "s3:GetLifecycleConfiguration", "s3:PutLifecycleConfiguration",
                     "s3:DeleteObject"},
    "S3FullAccessPolicy": {"s3:GetObject", "s3:GetObjectAcl", "s3:GetObjectVersion", "s3:PutObject", "s3:PutObjectAcl",
                           "s3:DeleteObject", "s3:DeleteObjectTagging", "s3:DeleteObjectVersionTagging",
                           "s3:GetObjectTagging", "s3:GetObjectVersionTagging", "s3:PutObjectTagging",
                           "s3:PutObjectVersionTagging", "s3:ListBucket", "s3:GetBucketLocation",
                           "s3:GetLifecycleConfiguration", "s3:PutLifecycleConfiguration"},
    "SQSSendMessagePolicy": {"sqs:SendMessage*"},
    "SQSPollerPolicy": {"sqs:ChangeMessageVisibility", "sqs:ChangeMessageVisibilityBatch", "sqs:DeleteMessage",
                        "sqs:DeleteMessageBatch", "sqs:GetQueueAttributes", "sqs:ReceiveMessage"},
    "SNSPublishMessagePolicy": {"sns:Publish"},
    "SNSCrudPolicy": {"sns:ListSubscriptionsByTopic", "sns:CreateTopic", "sns:SetTopicAttributes", "sns:Subscribe",
                      "sns:Publish"},
    "LambdaInvokePolicy": {"lambda:InvokeFunction"},
    "StepFunctionsExecutionPolicy": {"states:StartExecution"},
    "StepFunctionsCallbackPolicy": {"states:SendTaskSuccess", "states:SendTaskFailure", "states:SendTaskHeartbeat"},
    "AWSSecretsManagerGetSecretValuePolicy": {"secretsmanager:GetSecretValue"},
    "SSMParameterReadPolicy": {"ssm:DescribeParameters", "ssm:GetParameters", "ssm:GetParameter",
                               "ssm:GetParametersByPath"},
    "SSMParameterWithSlashPrefixReadPolicy": {"ssm:DescribeParameters", "ssm:GetParameters", "ssm:GetParameter",
                                              "ssm:GetParametersByPath"},
    "KMSDecryptPolicy": {"kms:Decrypt"},
    "KMSEncryptPolicy": {"kms:Encrypt"},
    "EventBridgePutEventsPolicy": {"events:PutEvents"},
    "FirehoseWritePolicy": {"firehose:PutRecord", "firehose:PutRecordBatch"},
    "SESCrudPolicy": {"ses:GetIdentityVerificationAttributes", "ses:SendEmail", "ses:SendRawEmail",
                      "ses:VerifyEmailIdentity"},
    "SESSendBouncePolicy": {"ses:SendBounce"},
    "SESBulkTemplatedCrudPolicy": {"ses:GetIdentityVerificationAttributes", "ses:SendEmail", "ses:SendRawEmail",
                                   "ses:SendTemplatedEmail", "ses:SendBulkTemplatedEmail", "ses:VerifyEmailIdentity"},
    "CloudWatchPutMetricPolicy": {"cloudwatch:PutMetricData"},
    "RekognitionDetectOnlyPolicy": {"rekognition:DetectFaces", "rekognition:DetectLabels",
                                    "rekognition:DetectModerationLabels", "rekognition:DetectText"},
    "TextractDetectAnalyzePolicy": {"textract:DetectDocumentText", "textract:StartDocumentTextDetection",
                                    "textract:StartDocumentAnalysis", "textract:AnalyzeDocument"},
    "TextractGetResultPolicy": {"textract:GetDocumentTextDetection", "textract:GetDocumentAnalysis"},
    "ComprehendBasicAccessPolicy": {"comprehend:BatchDetectKeyPhrases", "comprehend:DetectDominantLanguage",
                                    "comprehend:DetectEntities", "comprehend:BatchDetectEntities",
                                    "comprehend:DetectKeyPhrases", "comprehend:DetectSentiment",
                                    "comprehend:BatchDetectDominantLanguage", "comprehend:BatchDetectSentiment"},
    "EKSDescribePolicy": {"eks:DescribeCluster", "eks:ListClusters"},
    "EC2DescribePolicy": {"ec2:DescribeRegions", "ec2:DescribeInstances"},
    "AMIDescribePolicy": {"ec2:DescribeImages"},
    "CloudFormationDescribeStacksPolicy": {"cloudformation:DescribeStacks"},
    "ElasticsearchHttpPostPolicy": {"es:ESHttpPost", "es:ESHttpPut"},
}

_EVENT_GRANTS = {  # an event source's type -> what SAM lets the function do to read it
    "SQS": MANAGED_POLICIES["AWSLambdaSQSQueueExecutionRole"],
    "Kinesis": MANAGED_POLICIES["AWSLambdaKinesisExecutionRole"],
    "DynamoDB": MANAGED_POLICIES["AWSLambdaDynamoDBExecutionRole"],
}

_PYTHON_DEFAULT_TIMEOUT = 3  # seconds: CloudFormation's (and SAM's) Lambda timeout when none is set


def _managed(name: Any) -> set[str] | None:
    if not isinstance(name, str):
        return None
    return MANAGED_POLICIES.get(name.rsplit("/", 1)[-1])


def _sam_policies(policies: Any) -> tuple[set[str] | None, list[str]]:
    """
    What a function's Policies allow, and how the template names each: ({'sns:Publish'}, ['SNSPublishMessagePolicy']).
    None for the actions when one of them can't be told.
    """
    actions: set[str] | None = set()
    names: list[str] = []
    for policy in as_list(policies):
        found: set[str] | None = None
        if isinstance(policy, str):
            found = _managed(policy)
            names.append(policy.rsplit("/", 1)[-1])
        elif isinstance(policy, dict) and ("Statement" in policy or "PolicyDocument" in policy):
            found = statement_actions(policy.get("PolicyDocument", policy))
            names.append("an inline statement")
        elif isinstance(policy, dict) and len(policy) == 1:
            template = next(iter(policy))
            found = POLICY_TEMPLATES.get(template)
            names.append(template)
        if found is None:
            actions = None
        elif actions is not None:
            actions |= found
    return actions, names


def _role_actions(role: dict[str, Any]) -> set[str] | None:
    """
    What an AWS::IAM::Role in the template allows, from its inline policies and the managed ones it knows.
    """
    props = role.get("Properties") or {}
    actions: set[str] = set()
    for policy in as_list(props.get("Policies")):
        found = statement_actions((policy or {}).get("PolicyDocument")) if isinstance(policy, dict) else None
        if found is None:
            return None
        actions |= found
    for arn in as_list(props.get("ManagedPolicyArns")):
        found = _managed(arn) if isinstance(arn, str) else None
        if found is None:
            return None
        actions |= found
    return actions


def _logical(ref: Any) -> str | None:
    """
    The resource a !Ref or !GetAtt names: {'Fn::GetAtt': ['CartRole', 'Arn']} -> 'CartRole'.
    """
    if isinstance(ref, dict) and "Ref" in ref and isinstance(ref["Ref"], str):
        return ref["Ref"]
    if isinstance(ref, dict) and "Fn::GetAtt" in ref:
        value = ref["Fn::GetAtt"]
        return value[0] if isinstance(value, list) and value and isinstance(value[0], str) else None
    return None


class SamTemplate(Deploy):
    """
    template.yaml (or .yml, or .json): SAM and plain CloudFormation.
    """

    name = "sam"
    title = "AWS SAM"
    files = ("template.yaml", "template.yml", "template.json")

    def deployments(self, files: dict[str, str], code: set[str]) -> list[Deployment]:
        found: list[Deployment] = []
        for path, text in files.items():
            data = json.loads(text) if path.endswith(".json") else load_yaml(text)
            if not isinstance(data, dict) or not isinstance(data.get("Resources"), dict):
                continue
            found += self._functions(path, text, data, code)
        return found

    def _functions(self, path: str, text: str, data: dict[str, Any], code: set[str]) -> list[Deployment]:
        resources: dict[str, Any] = data["Resources"]
        base = posixpath.dirname(path)
        defaults = ((data.get("Globals") or {}).get("Function") or {})
        connected = any(isinstance(r, dict) and r.get("Type") == "AWS::Serverless::Connector"
                        for r in resources.values())
        found = []
        for logical_id, resource in resources.items():
            if not isinstance(resource, dict):
                continue
            kind = resource.get("Type")
            props = resource.get("Properties") or {}
            if kind not in ("AWS::Serverless::Function", "AWS::Lambda::Function") or props.get("PackageType") == "Image":
                continue
            merged = {**defaults, **props} if kind == "AWS::Serverless::Function" else dict(props)
            runtime = merged.get("Runtime")
            if isinstance(runtime, str) and not runtime.startswith("python"):
                continue
            code_dir = merged.get("CodeUri") if kind == "AWS::Serverless::Function" else merged.get("Code")
            where = resolve_handler(base, code_dir if isinstance(code_dir, str) else "", merged.get("Handler", ""), code)
            if where is None:
                continue
            env_names, env_error = set(), None
            for source in ((defaults if kind == "AWS::Serverless::Function" else {}), props):
                variables = ((source.get("Environment") or {}).get("Variables")) if isinstance(source, dict) else None
                if isinstance(variables, dict):
                    env_names |= {str(name) for name in variables}
                elif variables is not None:
                    env_error = "its Variables aren't written out"
            actions, names = self._permissions(logical_id, props, kind, resources)
            if connected:  # a Connector grants what it joins, which this doesn't read
                actions = None
            layers = [str(_logical(layer) or layer) for layer in as_list(merged.get("Layers"))]
            timeout = merged.get("Timeout", _PYTHON_DEFAULT_TIMEOUT)
            memory = merged.get("MemorySize", 128)
            found.append(Deployment(
                logical_id, path, self.name, where[0], where[1], "lambda", line_of(text, logical_id),
                runtime if isinstance(runtime, str) else None, timeout if isinstance(timeout, int) else None,
                memory if isinstance(memory, int) else None, env_names, env_error, layers, actions, names))
        return found

    def _permissions(self, logical_id: str, props: dict[str, Any], kind: str, resources: dict[str, Any]
                     ) -> tuple[set[str] | None, list[str]]:
        """
        What a function's role allows: SAM's role from its Policies and event sources, or a role in the template,
        plus any AWS::IAM::Policy attached to that role. None for the actions when it can't be told.
        """
        role_id = None
        names: list[str] = []
        if "Role" in props:
            role_id = _logical(props["Role"])
            role = resources.get(role_id) if role_id else None
            if not isinstance(role, dict) or role.get("Type") != "AWS::IAM::Role":
                return None, []
            actions = _role_actions(role)
            names.append(role_id or "")
        elif kind == "AWS::Serverless::Function":
            actions, names = _sam_policies(props.get("Policies"))
            role_id = f"{logical_id}Role"
            if actions is not None:
                actions |= MANAGED_POLICIES["AWSLambdaBasicExecutionRole"]
                for event in (props.get("Events") or {}).values():
                    if isinstance(event, dict):
                        actions |= _EVENT_GRANTS.get(event.get("Type", ""), set())
        else:
            return None, []
        for resource in resources.values():
            if not isinstance(resource, dict) or resource.get("Type") not in ("AWS::IAM::Policy",
                                                                              "AWS::IAM::ManagedPolicy"):
                continue
            policy = resource.get("Properties") or {}
            if any(_logical(role) == role_id for role in as_list(policy.get("Roles"))):
                more = statement_actions(policy.get("PolicyDocument"))
                actions = None if more is None or actions is None else actions | more
        return actions, names

    def grant(self, deployment: Deployment, actions: list[str]) -> str:
        """
        The smallest SAM policy template for each service's missing actions ('add DynamoDBWritePolicy and
        SNSPublishMessagePolicy'), and a statement for what none covers.
        """
        by_service: dict[str, list[str]] = {}
        for action in actions:
            by_service.setdefault(action.split(":")[0], []).append(action)
        templates, rest = [], []
        for wanted in by_service.values():
            fits = [(name, granted) for name, granted in POLICY_TEMPLATES.items()
                    if all(allowed(action, granted) for action in wanted)]
            if fits:
                templates.append(min(fits, key=lambda fit: (len(fit[1]), fit[0]))[0])
            else:
                rest += wanted
        where = f"{deployment.name}'s Policies in {deployment.source}"
        said = [" and ".join(templates)] if templates else []
        said += [f"a statement that allows {', '.join(rest)}"] if rest else []
        return f"add {' and '.join(said)} to {where}"
