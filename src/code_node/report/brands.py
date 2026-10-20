"""
Real logos for the graph's boxes, in two sizes, as favicons come: `full`, the detailed art, for 40 pixels and up
(a 2x screen's 32), and, for AWS's service icons, `small`, a simple mark that stays sharp at 16 to 32 (an ordinary
screen's badge). logo_for(name, pixels) picks one; the page's graph has both and picks by the screen's density.

Real logos for the graph's boxes: an AWS service's (S3, DynamoDB, SNS...) and those of the services libraries reach
(Redis, PostgreSQL, OpenAI...). The SVGs are gilbarbara/logos, CC0, through Iconify's @iconify-json/logos, kept as
files in logos/: scripts/logos.py downloads the pinned version and writes the ones named here. The page embeds the
ones it uses, so it stays one file that works offline. Each logo is its company's trademark, shown to name the
service the code reaches.
"""

from __future__ import annotations

import re
from functools import lru_cache
from importlib.resources import files
from typing import Any

from ..platforms.web import FRAMEWORK_LOGOS

AWS_LOGOS = {  # boto3's service name -> its logo
    "s3": "aws-s3",
    "s3control": "aws-s3",
    "dynamodb": "aws-dynamodb",
    "dynamodbstreams": "aws-dynamodb",
    "sns": "aws-sns",
    "sqs": "aws-sqs",
    "lambda": "aws-lambda",
    "kinesis": "aws-kinesis",
    "events": "aws-eventbridge",
    "stepfunctions": "aws-step-functions",
    "secretsmanager": "aws-secrets-manager",
    "ssm": "aws-systems-manager",
    "kms": "aws-kms",
    "ses": "aws-ses",
    "sesv2": "aws-ses",
    "rds": "aws-rds",
    "rds-data": "aws-rds",
    "redshift": "aws-redshift",
    "redshift-data": "aws-redshift",
    "athena": "aws-athena",
    "glue": "aws-glue",
    "ecs": "aws-ecs",
    "eks": "aws-eks",
    "ec2": "aws-ec2",
    "cloudwatch": "aws-cloudwatch",
    "logs": "aws-cloudwatch",
    "cognito-idp": "aws-cognito",
    "cognito-identity": "aws-cognito",
    "iam": "aws-iam",
    "sts": "aws-iam",
    "apigateway": "aws-api-gateway",
    "apigatewayv2": "aws-api-gateway",
    "apigatewaymanagementapi": "aws-api-gateway",
    "cloudfront": "aws-cloudfront",
    "route53": "aws-route53",
    "elasticache": "aws-elasticache",
    "docdb": "aws-documentdb",
    "neptune": "aws-neptune",
    "timestream-write": "aws-timestream",
    "timestream-query": "aws-timestream",
    "keyspaces": "aws-keyspaces",
    "batch": "aws-batch",
    "codebuild": "aws-codebuild",
    "codepipeline": "aws-codepipeline",
    "codedeploy": "aws-codedeploy",
    "codecommit": "aws-codecommit",
    "cloudformation": "aws-cloudformation",
    "xray": "aws-xray",
    "appsync": "aws-appsync",
    "mq": "aws-mq",
    "kafka": "aws-msk",
    "opensearch": "aws-open-search",
    "es": "aws-open-search",
    "acm": "aws-certificate-manager",
    "backup": "aws-backup",
    "glacier": "aws-glacier",
    "quicksight": "aws-quicksight",
    "wafv2": "aws-waf",
    "waf": "aws-waf",
    "cloudtrail": "aws-cloudtrail",
    "config": "aws-config",
    "lightsail": "aws-lightsail",
    "amplify": "aws-amplify",
    "appflow": "aws-appflow",
    "lakeformation": "aws-lake-formation",
    "shield": "aws-shield",
    "elbv2": "aws-elb",
    "elb": "aws-elb",
}

SERVICE_LOGOS = {  # a service a library reaches, as its box names it (lower case) -> its logo
    "redis": "redis",
    "postgresql": "postgresql",
    "mysql": "mysql-icon",
    "sqlite": "sqlite",
    "mongodb": "mongodb-icon",
    "openai": "openai-icon",
    "azure openai": "azure-icon",
    "anthropic": "anthropic-icon",
    "anthropic on bedrock": "anthropic-icon",
    "anthropic on vertex ai": "anthropic-icon",
    "kafka": "kafka-icon",
    "rabbitmq": "rabbitmq-icon",
    "snowflake": "snowflake-icon",
    "redshift": "aws-redshift",
    "elasticsearch": "elasticsearch",
    "mariadb": "mariadb-icon",
    "stripe": "stripe",
    "slack": "slack-icon",
    "twilio": "twilio-icon",
    "supabase": "supabase-icon",
    "firebase": "firebase-icon",
    "dynamodb": "aws-dynamodb",
    "s3": "aws-s3",
    "google cloud": "google-cloud",
    "google cloud storage": "google-cloud",
}


DEPLOY_LOGOS = {"sam": "aws-cloudformation", "serverless": "serverless"}  # a deploy plugin's name -> its logo

PLATFORM_LOGOS = {"lambda": "aws-lambda", "": "python"}  # a platform's name -> its logo ('' is plain Python); the
# web one's are by framework (platforms/web.py FRAMEWORK_LOGOS), shown on an app's box

LIBRARY_LOGOS = {  # a library plugin's name -> its logo, and boto3's, which the reader knows itself
    "boto3": "aws",
    "redis": "redis",
    "sql": "postgresql",
    "mongodb": "mongodb-icon",
    "llm": "openai-icon",
}


AWS_GLYPHS = {  # an AWS icon -> the symbol its small mark has, in white on the service's colour (AWS's own 16 px
    # icons are drawn that way); one not here gets 'cloud'
    "aws-s3": "bucket",
    "aws-glacier": "bucket",
    "aws-backup": "bucket",
    "aws-dynamodb": "database",
    "aws-rds": "database",
    "aws-aurora": "database",
    "aws-redshift": "database",
    "aws-timestream": "database",
    "aws-documentdb": "database",
    "aws-neptune": "database",
    "aws-elasticache": "database",
    "aws-keyspaces": "database",
    "aws-athena": "database",
    "aws-sqs": "queue",
    "aws-kinesis": "queue",
    "aws-mq": "queue",
    "aws-msk": "queue",
    "aws-sns": "send",
    "aws-eventbridge": "send",
    "aws-ses": "send",
    "aws-secrets-manager": "key",
    "aws-kms": "key",
    "aws-iam": "key",
    "aws-cognito": "key",
    "aws-systems-manager": "key",
    "aws-certificate-manager": "key",
    "aws-shield": "key",
    "aws-waf": "key",
    "aws-lambda": "function",
    "aws-step-functions": "flow",
    "aws-glue": "flow",
    "aws-batch": "flow",
    "aws-ecs": "flow",
    "aws-eks": "flow",
    "aws-codebuild": "flow",
    "aws-codepipeline": "flow",
    "aws-codedeploy": "flow",
    "aws-appflow": "flow",
    "aws-cloudformation": "flow",
    "aws-api-gateway": "http",
    "aws-cloudfront": "http",
    "aws-route53": "http",
    "aws-appsync": "http",
    "aws-elb": "http",
}

SMALL_UNDER = 40  # pixels: a logo drawn smaller than this uses its small mark, when it has one


def _read(path: Any) -> tuple[int, int, str] | None:
    if not path.is_file():
        return None
    found = re.fullmatch(r'\s*<svg[^>]*viewBox="0 0 (\d+) (\d+)"[^>]*>(.*)</svg>\s*', path.read_text("utf-8"), re.S)
    return (int(found.group(1)), int(found.group(2)), found.group(3)) if found else None


@lru_cache(maxsize=None)
def small_logo(name: str) -> tuple[int, int, str] | None:
    """
    A logo's small mark, from logos/small/<name>.svg: (width, height, its SVG body). None when it has none: only
    AWS's service icons do, the others being simple enough already.
    """
    if not re.fullmatch(r"[a-z0-9-]+", name or ""):
        return None
    return _read(files(__package__).joinpath("logos", "small", f"{name}.svg"))


def logo_for(name: str, pixels: float) -> tuple[int, int, str] | None:
    """
    The version of a logo for the pixels it's drawn at, as a browser picks a favicon: the small mark under
    SMALL_UNDER, when there is one, else the full art.
    """
    return (small_logo(name) if pixels < SMALL_UNDER else None) or logo(name)


@lru_cache(maxsize=None)
def logo(name: str) -> tuple[int, int, str] | None:
    """
    A logo by its name ('aws-s3'), or a plugin's icon when it names one: (width, height, its SVG body), read from
    logos/<name>.svg. None when there's no such logo.
    """
    if not re.fullmatch(r"[a-z0-9-]+", name or ""):
        return None
    return _read(files(__package__).joinpath("logos", f"{name}.svg"))


def fills(found: tuple[int, int, str]) -> bool:
    """
    Whether a logo is a coloured square of its own (AWS's service icons): drawn filling its badge, not on a tile,
    so it gets every pixel there is. Their fine lines blur together any smaller on a 1x screen.
    """
    width, height, body = found
    return width == height and f'd="M0 0h{width}v{height}H0z"' in body[:600]


def logo_names() -> set[str]:
    """
    Every logo the graph and the docs' figures draw: what scripts/logos.py keeps.
    """
    return (
        set(AWS_LOGOS.values())
        | set(SERVICE_LOGOS.values())
        | set(DEPLOY_LOGOS.values())
        | set(PLATFORM_LOGOS.values())
        | set(LIBRARY_LOGOS.values())
        | set(FRAMEWORK_LOGOS.values())
    )
