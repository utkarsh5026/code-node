"""
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

AWS_LOGOS = {  # boto3's service name -> its logo
    "s3": "aws-s3", "s3control": "aws-s3", "dynamodb": "aws-dynamodb", "dynamodbstreams": "aws-dynamodb",
    "sns": "aws-sns", "sqs": "aws-sqs", "lambda": "aws-lambda", "kinesis": "aws-kinesis", "events": "aws-eventbridge",
    "stepfunctions": "aws-step-functions", "secretsmanager": "aws-secrets-manager", "ssm": "aws-systems-manager",
    "kms": "aws-kms", "ses": "aws-ses", "sesv2": "aws-ses", "rds": "aws-rds", "rds-data": "aws-rds",
    "redshift": "aws-redshift", "redshift-data": "aws-redshift", "athena": "aws-athena", "glue": "aws-glue",
    "ecs": "aws-ecs", "eks": "aws-eks", "ec2": "aws-ec2", "cloudwatch": "aws-cloudwatch", "logs": "aws-cloudwatch",
    "cognito-idp": "aws-cognito", "cognito-identity": "aws-cognito", "iam": "aws-iam", "sts": "aws-iam",
    "apigateway": "aws-api-gateway", "apigatewayv2": "aws-api-gateway", "apigatewaymanagementapi": "aws-api-gateway",
    "cloudfront": "aws-cloudfront", "route53": "aws-route53", "elasticache": "aws-elasticache",
    "docdb": "aws-documentdb", "neptune": "aws-neptune", "timestream-write": "aws-timestream",
    "timestream-query": "aws-timestream", "keyspaces": "aws-keyspaces", "batch": "aws-batch",
    "codebuild": "aws-codebuild", "codepipeline": "aws-codepipeline", "codedeploy": "aws-codedeploy",
    "codecommit": "aws-codecommit", "cloudformation": "aws-cloudformation", "xray": "aws-xray",
    "appsync": "aws-appsync", "mq": "aws-mq", "kafka": "aws-msk", "opensearch": "aws-open-search",
    "es": "aws-open-search", "acm": "aws-certificate-manager", "backup": "aws-backup", "glacier": "aws-glacier",
    "quicksight": "aws-quicksight", "wafv2": "aws-waf", "waf": "aws-waf", "cloudtrail": "aws-cloudtrail",
    "config": "aws-config", "lightsail": "aws-lightsail", "amplify": "aws-amplify", "appflow": "aws-appflow",
    "lakeformation": "aws-lake-formation", "shield": "aws-shield", "elbv2": "aws-elb", "elb": "aws-elb",
}

SERVICE_LOGOS = {  # a service a library reaches, as its box names it (lower case) -> its logo
    "redis": "redis", "postgresql": "postgresql", "mysql": "mysql-icon", "sqlite": "sqlite",
    "mongodb": "mongodb-icon", "openai": "openai-icon", "azure openai": "azure-icon", "anthropic": "anthropic-icon",
    "anthropic on bedrock": "anthropic-icon", "anthropic on vertex ai": "anthropic-icon", "kafka": "kafka-icon",
    "rabbitmq": "rabbitmq-icon", "snowflake": "snowflake-icon", "redshift": "aws-redshift",
    "elasticsearch": "elasticsearch", "mariadb": "mariadb-icon", "stripe": "stripe", "slack": "slack-icon",
    "twilio": "twilio-icon", "supabase": "supabase-icon", "firebase": "firebase-icon", "dynamodb": "aws-dynamodb",
    "s3": "aws-s3", "google cloud": "google-cloud", "google cloud storage": "google-cloud",
}


DEPLOY_LOGOS = {"sam": "aws-cloudformation", "serverless": "serverless"}  # a deploy plugin's name -> its logo

PLATFORM_LOGOS = {"lambda": "aws-lambda", "": "python"}  # a platform's name -> its logo ('' is plain Python)

LIBRARY_LOGOS = {  # a library plugin's name -> its logo, and boto3's, which the reader knows itself
    "boto3": "aws", "redis": "redis", "sql": "postgresql", "mongodb": "mongodb-icon", "llm": "openai-icon",
}


@lru_cache(maxsize=None)
def logo(name: str) -> tuple[int, int, str] | None:
    """
    A logo by its name ('aws-s3'), or a plugin's icon when it names one: (width, height, its SVG body), read from
    logos/<name>.svg. None when there's no such logo.
    """
    if not re.fullmatch(r"[a-z0-9-]+", name or ""):
        return None
    path = files(__package__).joinpath("logos", f"{name}.svg")
    if not path.is_file():
        return None
    found = re.fullmatch(r'\s*<svg[^>]*viewBox="0 0 (\d+) (\d+)"[^>]*>(.*)</svg>\s*', path.read_text("utf-8"), re.S)
    return (int(found.group(1)), int(found.group(2)), found.group(3)) if found else None


def logo_names() -> set[str]:
    """
    Every logo the graph and the docs' figures draw: what scripts/logos.py keeps.
    """
    return (set(AWS_LOGOS.values()) | set(SERVICE_LOGOS.values()) | set(DEPLOY_LOGOS.values())
            | set(PLATFORM_LOGOS.values()) | set(LIBRARY_LOGOS.values()))
