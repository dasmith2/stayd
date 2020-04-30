""" Brace yourself, S3 configuration has quite the learning curve. There are
not one, not two, but five places you have to configure permissions precisely
in order for this to work. If you have anything wrong, you're liable to get 403
forbidden errors when you try to do anything, but these errors contain no
information. Good luck! :D

It all starts with the AWS console at https://us-east-2.console.aws.amazon.com
The two important services are S3 and IAm. For PUBLIC stuff, log in with the
publics3@hihoward.com account whose password is in keeper.

Type S3 in the services box. You'll notice the prod-hihoward-public bucket.
This is where all the photos with publically viewable urls go in production.
Now, when it comes to websites being allowed to do things to photos in an S3
bucket, click on the bucket -> Permissions -> CORS configuration. Yep, it's a
text file, an XML file to be exact, and you have to configure domains and
verbs.

Now, I could have sworn I uploaded publically readable photos without this here
paragraph before. When you presign a post, you get to specify ACLs. I'll get to
that in a bit. So I THOUGHT I was just setting those to allow public read. But,
that no longer works. So when I made a bucket policy that allowed public read,
I could finally reliably public read. Amazon S3 -> your bucket -> permissions
-> bucket policy, and then here's an example of how to set it up so anybody can
read anything from the bucket:

https://docs.aws.amazon.com/AmazonS3/latest/dev/example-bucket-policies.html#example-bucket-policies-use-case-2

There's one more set of particularly confusingly explained security settings on
the bucket level. At least these are just checkboxes.  bucket -> Permissions ->
Block public access.  The only policy you can leave on, I believe, is "Block
public access to buckets and objects granted through new public bucket
policies." But if you're getting 403s you may need to fuss with this too.
Honestly I really don't understand these.

But that's not the whole picture, not by a long shot. The public can't just
upload whatever it wants with a simple post now, no no. Each upload has to
get signed by somebody with permission to the bucket. If THAT isn't set up
correctly, you'll STILL get 403 forbidden errors.

Head back to the main console but this time type iam in the find services box.
Click around and find the IAm user creatively named
hihowardiam.  Click in and check out the permissions tab. This user has a
permission policy (increasingly innapropriately) called
put-prod-hihoward-public, which you can click on. This policy is ANOTHER text
file, this time in json! (I hate inconsistency. Isn't inconsistency the best?)
This time we have ACLs which stands for Access c??? list? Anyway, they're
basically verbs. You also say what the user can verb.  Careful, it's tricky
because you need some ACLs for the objects in the bucket, which is what
arn:aws:s3:::prod-hihoward-public/* refers to, and some ACLs on the bucket
itself, arn:aws:s3:::prod-hihoward-public. If you're missing ANY ACL you'll
get, you guessed it, 403 forbidden explanation-less errors.

OK hihowardiam has credentials including a secret access key, and an access
key id. You can see these being used in use in this file as
settings.S3_ACCESS_KEY_ID_SENSITIVE and S3_SECRET_ACCESS_KEY_SENSITIVE

Now, I logged in as publics3@hihoward.com, who is therefore a root user. You
CAN give your root user keys, but you don't want to. The reason I created an
IAm user instead of just giving publics3@hihoward.com keys is, the risk of
what happens if the keys are stolen. The IAm user has very limited permissions,
so if its keys are stolen, pretty much all you could do would be, like, delete
our images or something. Not the end of the world. If publics3@hihoward.com's
keys existed and got stolen, that's root access, and the hacker could sign up
for and use services.

Aaaaand there's one more thing to consider. When you sign the metadata for a
photo so it can upload to S3, you specify what the ACL ought to be for that
photo. That is, permissions are also set on the object level, and that can
block, say, the public's ability to read the file. I think. """
import base64
import os
import re

import boto3
import botocore
from django.conf import settings
from django.db import models
from django.shortcuts import reverse

from errors.models import log_error


# You need signature_version='s3v4' to avoid
# "The authorization mechanism you have provided is not supported. Please use
# AWS4-HMAC-SHA256
_config = botocore.client.Config(
    signature_version='s3v4',
    region_name='us-east-2')


_s3_sensitive = boto3.client(
    's3',
    aws_access_key_id=settings.S3_ACCESS_KEY_ID_SENSITIVE,
    aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY_SENSITIVE,
    config=_config)


_s3_public = boto3.client(
    's3',
    aws_access_key_id=settings.S3_ACCESS_KEY_ID_PUBLIC,
    aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY_PUBLIC,
    config=_config)


def photo_url(file_name, sensitive):
  if sensitive:
    # For sensitive images, they have to get the bytes through keys, which
    # does a permissions check. In fact if you try to return the s3.amazonaws
    # link for a sensitive image, the user won't be able to see it because
    # CORS is turned off for that bucket. The ONLY way to access the bytes of
    # a sensitive image is through keys.
    return reverse(
        'view_sensitive_image', kwargs={'file_name': file_name})
  return 'https://{}.s3.amazonaws.com/{}'.format(
      settings.S3_BUCKET_NAME_PUBLIC, file_name)


class S3(object):
  def __init__(self, sensitive, s3_override=None):
    """ s3_override is so you can pass in a mock for tests. """
    self.sensitive = sensitive
    if sensitive:
      self._s3 = _s3_sensitive
      self._s3_bucket = settings.S3_BUCKET_NAME_SENSITIVE
    else:
      self._s3 = _s3_public
      self._s3_bucket = settings.S3_BUCKET_NAME_PUBLIC
    if s3_override:
      self._s3 = s3_override
    elif settings.TEST:
      raise Exception(
          'You should use a mock s3 object in tests by passing in an '
          's3_override')

  def list(self):
    """ [('blahblahblah.jpg', datetime(2018, 6, 28, 21)),
         (file name, last modified)] """
    to_return = []
    # You don't have to can_read_net here. __init__ forces tests to pass in an
    # s3_override, and  dev and stage use the dev s3 buckets.
    lookup_result = self._s3.list_objects_v2(Bucket=self._s3_bucket)
    # If the bucket is empty they omit the Contents entirely.
    if 'Contents' in lookup_result:
      for obj in lookup_result['Contents']:
        to_return.append((obj['Key'], obj['LastModified']))
    return to_return

  def download(self, file_name, local_file_name=None):
    local_file_name = local_file_name or file_name
    self._s3.download_file(self._s3_bucket, file_name, local_file_name)

  def rm_download(self, local_file_name):
    os.remove(local_file_name)

  def image_bytes(self, file_name):
    """
    return HttpResponse(S3().image_bytes(file_name), content_type='image/jpeg')
    """
    if re.compile(r'[\/\\]').search(file_name):
      raise Exception(
          'I\'m expecting simply a file_name I can download, '
          'not a path to a file that\'s already downloaded.')
    for tries in range(3):
      if not os.path.exists(file_name):  # More or less always.
        # This throws an exception if the file doesn't exist on S3.
        self.download(file_name)
      # So if we get here, we know the file exists on S3. So far so good. But
      # one time, this open call here triggered a FileNotFoundError. Now, I
      # could see that happening if somebody opens a pile of tabs that all try
      # to load this image at once, and then there's a race where
      # os.path.exists at first but then before open gets called, a different
      # thread runs os.remove. My answer is to take 3 tries to load an image.
      try:
        f = open(file_name, 'rb')
      except FileNotFoundError:
        continue
      read = f.read()
      f.close()
      self.rm_download(file_name)
      return read
    log_error('Never able to download and read an image', (
        'I tried 3 times to download and read {}').format(file_name))

  def utf8_encoded_image(self, file_name):
    return base64.b64encode(self.image_bytes(file_name)).decode('utf-8')

  def upload(self, file_name, remote_file_name=None):
    remote_file_name = remote_file_name or file_name
    self._s3.upload_file(file_name, self._s3_bucket, remote_file_name)

  def delete(self, file_name):
    """ Regardless of whether file_name exists or not in the bucket, this will
    return a 204. """
    got = self._s3.delete_object(Bucket=self._s3_bucket, Key=file_name)
    return got['ResponseMetadata']['HTTPStatusCode'] == 204

  def generate_presigned_post(self, file_name, file_type):
    SignedPhoto.objects.get_or_create(
        file_name=file_name, sensitive=self.sensitive)
    fields = {'Content-Type': file_type}
    conditions = [{'Content-Type': file_type}]
    if not self.sensitive:
      # I could have sworn this used to work, but now it doesn't seem to. It's
      # not until you also add an S3 -> your bucket -> security -> bucket
      # policy that it becomes possible to publically read stuff out of a
      # bucket.
      fields['acl'] = 'public-read'
      conditions.insert(0, {'acl': 'public-read'})
    return self._s3.generate_presigned_post(
        Bucket=self._s3_bucket,
        Key=file_name,
        Fields=fields,
        Conditions=conditions,
        ExpiresIn=3600)


class SignedPhoto(models.Model):
  """ In order to upload a photo, keys must first sign it. I take that
  opportunity to keep track of all the photos that get signed and uploaded so I
  can circle back around later and delete anything that didn't end up in the
  Photos table, which is the list of photos that are actually getting used for
  anything. """
  file_name = models.CharField(max_length=200)
  sensitive = models.BooleanField()
  created_at = models.DateTimeField(auto_now_add=True)

  def delete_file(self, s3=None):
    s3 = s3 or S3(sensitive=self.sensitive)
    s3.delete(self.file_name)

  def url(self):
    return photo_url(self.file_name, self.sensitive)

  def __repr__(self):
    return '<SignedPhoto {}: {}>'.format(self.pk, self.file_name)
