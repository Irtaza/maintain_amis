# 1. This Lambda function creates backup AMIs of all EC2 instances that have a tag with key Backup and value True.
# 2. The function also takes the value of tag Retention from the EC2 instances that specifies the number of days
# a backup AMI of the EC2 instance should be kept for. This value is then used to add a tag with key DeleteOn
# to each backup AMI created with a value that contains the date on or after which the backup AMI should be deleted.
# 3. The function also deletes all backup AMIs and their corresponding EBS snapshots that have a DeleteOn tag value
# less than the execution date of the function.


import boto3
import datetime
import logging

# Set log level
logging.basicConfig()
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def flatten_list(list_to_flatten):
    """
    Flattens a list of list into a simple list
    :param list_to_flatten: The list of lists to flatten
    :return: A flattened list
    """
    return [item for sublist in list_to_flatten for item in sublist]


def get_instances_by_tag_keys(ec2_client):
    """
    Gets instances that have a tag Backup with a value of True
    :param ec2_client: A low-level client representing Amazon Elastic Compute Cloud (EC2)
    :return: A list of instances that describe each instance
    """
    reservations_list = ec2_client.describe_instances(
        Filters=[
            {'Name': 'tag:Backup', 'Values': ['Yes']},
        ]
    )['Reservations']

    instances_list = [i['Instances'] for i in reservations_list]

    return flatten_list(instances_list)


def get_instance_name(instance):
    """
    Returns the value of the Name tag of an instance
    :param instance: The instance object (a dict that describes the image)
    :return: The instance name
    """
    try:
        instance_name = [(tag['Value']) for tag in instance['Tags'] if tag['Key'] == 'Name'][0]
    except IndexError:
        instance_name = "Not Specified"

    logger.info("Instance {} has the Name tag of {}".format(instance['InstanceId'], instance_name))
    return instance_name


def get_instance_retention_days(instance):
    """
    Looks for Retention tag and returns its value - this value specifies the time period in days an image should be
    retained.
    :param instance: The instance object (a dict that describes the image)
    :return: The number of days an image of this instance should be retained for
    """
    try:
        retention_days = [int(tag['Value']) for tag in instance['Tags'] if tag['Key'] == 'Retention'][0]
    except IndexError:
        retention_days = 7

    logger.info("Instance {} to be retained for {} days".format(instance['InstanceId'], retention_days))
    return retention_days


def create_ami(ec2_client, instance_id, instance_name):
    """
    Create an ami from an existing instance
    :param ec2_client: A low-level client representing Amazon Elastic Compute Cloud (EC2)
    :param instance_id: The Id of the instance that will be used to create the AMI
    :param instance_name: The name of the instance that will be used to create the AMI
    :return: A list of image resources - the list should only contain one image
    """
    create_time = datetime.datetime.now().strftime('%Y%m%d%H%M%S')

    ami = ec2_client.create_image(InstanceId=instance_id,
                                  Name="{}-{}-{}".format(instance_name, instance_id, create_time),
                                  Description="AMI of instance {} with instance id {} created by Lambda on {}".format(
                                      instance_name, instance_id, create_time
                                  ), NoReboot=True, DryRun=False)
    logger.info("AMI of instance {} with instance id {} created by Lambda on {}".format(
        instance_name, instance_id, create_time))
    return ami


def create_ami_tags(ec2_client, image_id, retention_days):
    """
    Adds a tag DeleteOn to an AMI that has the value of a date on which the image needs to be deleted
    :param ec2_client: A low-level client representing Amazon Elastic Compute Cloud (EC2)
    :param image_id: The id of the image to which tags are to be added
    :param retention_days: The number of days for which the image should be retained.
    :return:
    """
    deregister_on = (datetime.date.today() + datetime.timedelta(days=retention_days)).strftime('%Y%m%d%H%M%S')

    ec2_client.create_tags(Resources=[image_id], Tags=[
        {'Key': 'DeleteOn', 'Value': deregister_on},
    ]
                           )
    logger.info("DeleteOn tag with value {} created for AMI Id {}".format(deregister_on, image_id))


def create_backup_amis(ec2_client):
    """
    This function calls all other functions required to create AMIs of instances with Backup tag with value set to True
    :param ec2_client: A low-level client representing Amazon Elastic Compute Cloud (EC2)
    :return: N/A
    """
    instances_list = get_instances_by_tag_keys(ec2_client)
    logger.info("Instances with Backup tag: {}".format(instances_list))
    for instance in instances_list:
        instance_id = instance['InstanceId']
        instance_name = get_instance_name(instance)
        retention_days = get_instance_retention_days(instance)
        ami = create_ami(ec2_client, instance_id, instance_name)
        create_ami_tags(ec2_client, ami['ImageId'], retention_days)


def get_amis_with_deleteon_tag(ec2_resource):
    """
    Gets all images that have the "DeleteOn" tag
    :param ec2_resource: A resource representing Amazon Elastic Compute Cloud (EC2)
    :return: A list of Image resources
    """
    return ec2_resource.images.filter(Owners=["self"], Filters=[
        {'Name': 'tag-key', 'Values': ['DeleteOn']}, ])


def get_list_of_images_to_deregister(amis_with_deleteon_tag):
    """
    Get list of AMIs that have the DeleteOn tag then check the value of the DeleteOn tag. If the value is less
    than the execution date that AMI is added to a list of AMIs to delete.
    :param amis_with_deleteon_tag: A list of AMIs that have the DeleteOn tag
    :return: A list of AMIs to delete
    """
    amis_to_delete = []
    for image in amis_with_deleteon_tag:
        try:
            if image.tags is not None:
                deletion_date = [
                    t.get('Value') for t in image.tags
                    if t['Key'] == 'DeleteOn'][0]
        except IndexError:
            deletion_date = False

        todays_date = datetime.datetime.now().strftime('%Y%m%d%H%M%S')

        if deletion_date <= todays_date:
            amis_to_delete.append(image.id)

    return amis_to_delete


def delete_snapshots(ec2_client, amis_to_delete):
    """
    Takes a list of AMIs to delete and then deletes the EBS snapshots linked to those AMIs
    :param ec2_client: A low-level client representing Amazon Elastic Compute Cloud (EC2)
    :param amis_to_delete: List of AMIs to delete
    :return: N/A
    """
    security_token = boto3.client('sts').get_caller_identity()['Account']
    snapshots = ec2_client.describe_snapshots(MaxResults=1000, OwnerIds=[security_token])['Snapshots']

    for snapshot in snapshots:
        if snapshot['Description'].find(amis_to_delete) > 0:
            snapshot_resposne = ec2_client.delete_snapshot(SnapshotId=snapshot['SnapshotId'])
            logger.info("Deleting snapshot " + snapshot['SnapshotId'])


def deregister_amis(ec2_client, amis_to_delete):
    """
    Takes a list of AMIs to delete, deregister those AMIs and their corresponding EBS snapshots
    :param ec2_client: A low-level client representing Amazon Elastic Compute Cloud (EC2)
    :param amis_to_delete: List of AMIs to delete
    :return: N/A
    """
    for ami in amis_to_delete:
        logger.info("Deregistering AMI {}".format(ami))
        ami_response = ec2_client.deregister_image(
            DryRun=False,
            ImageId=ami,
        )

        delete_snapshots(ec2_client, ami)


def deregister_backup_amis(ec2_resource, ec2_client):
    """
    Gets AMIs that have a DeleteOn tag value greater than the execution date of this function and then deregisters them
    :param ec2_resource: A resource representing Amazon Elastic Compute Cloud (EC2)
    :param ec2_client: A low-level client representing Amazon Elastic Compute Cloud (EC2)
    :return: N/A
    """
    amis = get_amis_with_deleteon_tag(ec2_resource)
    amis_to_delete = get_list_of_images_to_deregister(amis)
    logger.info(amis_to_delete)

    deregister_amis(ec2_client, amis_to_delete)


def lambda_handler(event, context):
    """
    The entry point for the lambda that calls two functions - first one creates AMIs marked for backup and
    the other removes AMIs that have expired
    :param event:
    :param context:
    :return: N/A
    """
    ec2_client = boto3.client('ec2')
    ec2_resource = boto3.resource('ec2')

    create_backup_amis(ec2_client)
    deregister_backup_amis(ec2_resource, ec2_client)