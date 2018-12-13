provider "aws" {
  region = "eu-west-2"
}

resource "aws_lambda_function" "maintain_amis" {
  function_name = "maintain-amis"

  # The bucket that contains the lambda source code
  s3_bucket = "irtaza-code-repo"
  s3_key    = "lambda/maintain_amis/v1.0.0/maintain_amis.zip"

  # "lambda_function" is the filename within the zip file (lambda_function.py)
  # and "lambda_handler" is the name of the method where the lambda starts
  handler = "lambda_function.lambda_handler"

  runtime = "python3.6"
  timeout = "600"

  role = "${aws_iam_role.lambda_exec.arn}"
}

# IAM role which dictates what other AWS services the Lambda function
# may access.
resource "aws_iam_role" "lambda_exec" {
  name = "maintain_amis_lambda_role"

  assume_role_policy = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Action": "sts:AssumeRole",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Effect": "Allow",
      "Sid": ""
    }
  ]
}
EOF
}

# IAM policy that allows the maintain_amis_lambda_role to get required
# permissions
resource "aws_iam_policy" "policy" {
  name        = "maintain_amis_policy"
  description = "A policy for creating and deleing AMIs via Lambda"

  path   = "/"
  policy = "${data.aws_iam_policy_document.policy_document.json}"
}

# Generate json policy document for maintain_amis_policy
data "aws_iam_policy_document" "policy_document" {
  statement {
    sid = "1"

    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "ec2:CreateImage",
      "ec2:CreateTags",
      "ec2:DescribeSnapshots",
      "ec2:DeleteSnapshot",
      "ec2:DeregisterImage",
      "ec2:DescribeImages",
      "ec2:DescribeInstances",
    ]

    resources = [
      "*",
    ]
  }
}

# Attach policy to to IAM role
resource "aws_iam_policy_attachment" "policy_attach" {
  name       = "policy_attachment"
  roles      = ["${aws_iam_role.lambda_exec.name}"]
  policy_arn = "${aws_iam_policy.policy.arn}"
}

# Creates a cloudwatch event ruke
resource "aws_cloudwatch_event_rule" "every-saturday-three-am" {
  name                = "every-saturday-three-am"
  description         = "Fires every Saturday at 3 am"
  schedule_expression = "cron(0 3 ? * SAT *)"
}

# Links the lambda function to the cloudwatch rule
resource "aws_cloudwatch_event_target" "check_manintain_amis_staurday_three_am" {
  rule      = "${aws_cloudwatch_event_rule.every-saturday-three-am.name}"
  target_id = "maintain_amis"
  arn       = "${aws_lambda_function.maintain_amis.arn}"
}

# Grant permission to Cloudwatch to involke the lambda function
resource "aws_lambda_permission" "allow_cloudwatch_to_call_check_maintain_amis" {
  statement_id  = "AllowExecutionFromCloudWatch"
  action        = "lambda:InvokeFunction"
  function_name = "${aws_lambda_function.maintain_amis.function_name}"
  principal     = "events.amazonaws.com"
  source_arn    = "${aws_cloudwatch_event_rule.every-saturday-three-am.arn}"
}
