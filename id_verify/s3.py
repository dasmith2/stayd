import boto3
import botocore

from django.conf import settings


# You need signature_version='s3v4' to avoid
# "The authorization mechanism you have provided is not supported. Please use
# AWS4-HMAC-SHA256
_config = botocore.client.Config(
    signature_version='s3v4',
    region_name='us-east-2')


_s3 = boto3.client(
    's3',
    aws_access_key_id=settings.S3_ACCESS_KEY_ID,
    aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY,
    config=_config)


class S3(object):
  def generate_presigned_post(self, **kwargs):
    return _s3.generate_presigned_post(**kwargs)

  def list(self):
    """ [('blahblahblah.jpg', datetime(2018, 6, 28, 21)),
         (file name, last modified)] """
    to_return = []
    lookup_result = _s3.list_objects_v2(Bucket=settings.S3_BUCKET_NAME)
    # If the bucket is empty they omit the Contents entirely.
    if 'Contents' in lookup_result:
      for obj in lookup_result['Contents']:
        to_return.append((obj['Key'], obj['LastModified']))
    return to_return

  def download(self, file_name, local_file_name=None):
    local_file_name = local_file_name or file_name
    _s3.download_file(settings.S3_BUCKET_NAME, file_name, local_file_name)

  def upload(self, file_name, remote_file_name=None):
    remote_file_name = remote_file_name or file_name
    _s3.upload_file(file_name, settings.S3_BUCKET_NAME, remote_file_name)

  def delete(self, file_name):
    got = _s3.delete_object(Bucket=settings.S3_BUCKET_NAME, Key=file_name)
    return got['ResponseMetadata']['HTTPStatusCode'] == 204
