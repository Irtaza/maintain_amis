# Automate AMI backups of AWS EC2 instances using Lambda and deploy it using Terraform

The code in `lambda_function.py` creates automated backups of EBS backed EC2 instances on a schedule and deletes old AMIs and
their corresponding EBS snapshots. A summary of features of this code:

1. Create backup AMIs of all EC2 instances that have a tag with key `Backup` and value `True`.
2. Take the value of tag `Retention` from the EC2 instances that specifies the number of days
a backup AMI of the EC2 instance should be kept for. This value is then used to add a tag with key DeleteOn
to each backup AMI created with a value that contains the date on or after which the backup AMI should be deleted.
3. Delete all backup AMIs and their corresponding EBS snapshots that have a `DeleteOn` tag value
less than the execution date of the function.

The file `lambda.tf` contains the Terraform script used to deploy this function. The script includes:

1. Create IAM Roles and Policies
2. Create Lambda function 
3. Create a Cloudwatch event rule to trigger the Lambda fucntion once a week