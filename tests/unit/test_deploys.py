"""
Deploy files: SAM and serverless.yml, and the roles they give.
"""

from __future__ import annotations

from pathlib import Path

from code_node.analysis.graph import code_graph
from code_node.project import entry_points, read_project

from support import write


SAM = {
    "template.yaml": """
Transform: AWS::Serverless-2016-10-31
Globals:
  Function:
    Runtime: python3.13
    Environment:
      Variables:
        STAGE: prod
Resources:
  ResizeFunction:
    Type: AWS::Serverless::Function
    Properties:
      CodeUri: src/
      Handler: images.resize.run
      Timeout: 20
      Layers:
        - !Ref PillowLayer
      Policies:
        - S3ReadPolicy:
            BucketName: !Ref Uploads
        - Statement:
            - Effect: Allow
              Action: sqs:SendMessage
              Resource: "*"
  Uploads:
    Type: AWS::S3::Bucket
""",
    "src/images/__init__.py": "",
    "src/images/resize.py": """
import os
import boto3
import PIL

s3 = boto3.client("s3")


def run(event, context):
    s3.get_object(Bucket=os.environ["BUCKET"], Key="a")
    s3.put_object(Bucket=os.environ["STAGE"], Key="b", Body=b"")
    boto3.client("sqs").send_message(QueueUrl="q", MessageBody="done")
""",
}


def test_a_sam_template_names_the_entry_point_and_what_its_role_allows(tmp_path: Path) -> None:
    from code_node.analysis.findings import code_map_findings
    from code_node.pages import PageOptions, map_entry

    root = write(tmp_path, SAM)
    project = read_project(root)
    assert list(project.deploy_files) == ["template.yaml"]
    found = entry_points(project)
    # run() isn't named like a handler: the template is what says it is one
    assert [(e.name, e.why, e.platform) for e in found] == [
        ("images.resize.run", "ResizeFunction in template.yaml", "lambda")
    ]
    cmap, _ = map_entry(root, found[0], PageOptions())
    fn = cmap.function
    assert (fn.name, fn.runtime, fn.timeout, fn.env_names, fn.layers) == (
        "ResizeFunction",
        "python3.13",
        20,
        {"STAGE"},
        ["PillowLayer"],
    )
    assert {i.top: i.source for i in cmap.imports}["PIL"] == "package"
    said = " ".join(message for _, message in code_map_findings(cmap))
    assert "BUCKET isn't set on ResizeFunction" in said and "STAGE isn't" not in said
    assert (
        "ResizeFunction's role in template.yaml (it has S3ReadPolicy and an inline statement) doesn't allow "
        "s3:PutObject"
    ) in said
    assert "Add S3WritePolicy to ResizeFunction's Policies in template.yaml" in said
    s3 = next(n for n in code_graph(cmap).nodes if n.label == "S3")
    assert s3.flags == {"PutObject": "not allowed"} and s3.tone == "warn"
    assert next(n for n in code_graph(cmap).nodes if n.label == "SQS").tone == ""  # the inline statement allows it


def test_a_role_it_cant_read_leaves_permissions_unchecked(tmp_path: Path) -> None:
    from code_node.analysis.findings import code_map_findings
    from code_node.pages import PageOptions, map_entry

    files = dict(SAM)
    files["template.yaml"] = files["template.yaml"].replace(
        "      Policies:", "      Role: arn:aws:iam::123456789012:role/shared\n      Policies:"
    )
    root = write(tmp_path, files)
    cmap, _ = map_entry(root, entry_points(read_project(root))[0], PageOptions())
    assert cmap.function.permissions is None
    assert "doesn't allow" not in " ".join(message for _, message in code_map_findings(cmap))


def test_serverless_yml_names_the_entry_point(tmp_path: Path) -> None:
    from code_node.analysis.findings import code_map_findings
    from code_node.pages import PageOptions, map_entry

    root = write(
        tmp_path,
        {
            "serverless.yml": """
service: jobs
provider:
  name: aws
  runtime: python3.12
  environment:
    TABLE: jobs
  iam:
    role:
      statements:
        - Effect: Allow
          Action: [dynamodb:GetItem, dynamodb:Query]
          Resource: "*"
functions:
  sweep:
    handler: jobs/sweep.go
""",
            "jobs/__init__.py": "",
            "jobs/sweep.py": (
                "import os\nimport boto3\n\n\ndef go(event, context):\n"
                '    boto3.resource("dynamodb").Table(os.environ["TABLE"]).delete_item(Key={})\n'
            ),
        },
    )
    found = entry_points(read_project(root))
    assert [(e.name, e.why) for e in found] == [("jobs.sweep.go", "sweep in serverless.yml")]
    cmap, _ = map_entry(root, found[0], PageOptions())
    assert (cmap.function.timeout, cmap.function.env_names) == (6, {"TABLE"})
    said = " ".join(message for _, message in code_map_findings(cmap))
    assert "sweep's role in serverless.yml" in said and "dynamodb:DeleteItem" in said
    assert "Add a statement that allows dynamodb:DeleteItem to provider.iam.role.statements" in said


def test_iam_actions_match_with_their_wildcards() -> None:
    from code_node.deploys import allowed

    assert allowed("s3:GetObject", ["s3:Get*"]) and allowed("S3:getobject", ["s3:GetObject"])  # IAM ignores case
    assert allowed("dynamodb:Query", ["*"]) and not allowed("s3:PutObject", ["s3:Get*", "sqs:*"])


def test_a_policy_s_actions_or_none_when_they_cant_be_told() -> None:
    from code_node.deploys import statement_actions

    allow = {"Statement": [{"Effect": "Allow", "Action": ["s3:GetObject", "dynamodb:*"], "Resource": "*"}]}
    assert statement_actions(allow) == {"s3:GetObject", "dynamodb:*"}
    assert statement_actions([{"Effect": "Deny", "Action": "s3:*"}]) is None
    assert statement_actions({"Effect": "Allow", "NotAction": "iam:*"}) is None
    assert statement_actions({"Effect": "Allow", "Action": {"Ref": "Actions"}}) is None  # not written out


def test_a_handler_setting_names_its_file() -> None:
    from code_node.deploys import resolve_handler

    assert resolve_handler("", "src/", "cart.app.on_checkout", {"src/cart/app.py"}) == (
        "src/cart/app.py",
        "on_checkout",
    )
    assert resolve_handler("infra", "../src", "a.handler", {"src/a.py"}) == ("src/a.py", "handler")
    assert resolve_handler("", "", "pkg.handler", {"pkg/__init__.py"}) == ("pkg/__init__.py", "handler")
    assert resolve_handler("", "", "handler", {"handler.py"}) is None  # no module
    assert resolve_handler("", "", "gone.handler", {"handler.py"}) is None


def test_yaml_is_read_with_cloudformation_s_tags() -> None:
    from code_node.deploys import line_of, load_yaml

    text = "a: !Ref B\nb: !GetAtt R.Arn\nc: !Sub 'x-${AWS::Region}'\nd: !Join [',', [a, b]]\ne: ${self:service}\n"
    assert load_yaml(text) == {
        "a": {"Ref": "B"},
        "b": {"Fn::GetAtt": ["R", "Arn"]},
        "c": {"Fn::Sub": "x-${AWS::Region}"},
        "d": {"Fn::Join": [",", ["a", "b"]]},
        "e": "${self:service}",  # serverless.yml's variables stay as text
    }
    assert load_yaml("a: [\n") is None
    text = "Resources:\n  CartFunction:\n    Type: x\n  'Other': 1\n"
    assert (line_of(text, "CartFunction"), line_of(text, "Other"), line_of(text, "Missing")) == (2, 4, 0)
    assert line_of(text, "CartFunction", indent=0) == 0  # only at the top level
