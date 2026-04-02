from django.core.management.base import BaseCommand
from django.conf import settings
from api.models import User
import cloudinary
from cloudinary import api as cloudinary_api
from urllib.parse import urlparse


class Command(BaseCommand):
    help = (
        "Ensure all User.profile_imagen and banner_imagen fields are stored as "
        "full Cloudinary URLs. Converts any remaining public_id values by "
        "querying Cloudinary once and writing back the secure_url."
    )

    def handle(self, *args, **options):
        users = User.objects.all()
        count = 0
        for user in users:
            changed = False

            # profile image
            pi = getattr(user, 'profile_imagen', None)
            if pi and isinstance(pi, str) and not pi.startswith(('http://', 'https://')):
                # build url from cloudinary API using profile account
                cfg = settings.CLOUDINARY_STORAGE
                cloudinary.config(
                    cloud_name=cfg['CLOUD_NAME'],
                    api_key=cfg['API_KEY'],
                    api_secret=cfg['API_SECRET'],
                )
                try:
                    info = cloudinary_api.resource(pi)
                    url = info.get('secure_url') or info.get('url')
                    if url:
                        user.profile_imagen = url
                        changed = True
                        self.stdout.write(f"updated profile for {user.email} -> {url}")
                except Exception as e:
                    self.stderr.write(f"unable to fetch profile url for {pi}: {e}")

            # banner image (public_id or even malformed URL)
            bi_value = getattr(user, 'banner_imagen', None)
            if bi_value:
                # convert ImageFieldFile to string if necessary
                bi_str = str(bi_value)
                # determine raw public_id from whatever form we have
                def extract_public_id(value: str) -> str:
                    """Return a Cloudinary public_id from either a raw ID or a URL.
                    The URL may include the cloud name, the `/image/upload/` segment,
                    an optional `v1234/` version, and an extension.  We strip all of
                    that so the remaining string can be passed to the API's resource
                    method.
                    """
                    if not value.startswith(('http://', 'https://')):
                        return value
                    parsed = urlparse(value)
                    path = parsed.path or ''
                    # look for the upload segment; ignore anything before it
                    idx = path.find('/upload/')
                    if idx != -1:
                        path = path[idx + len('/upload/'):]
                    else:
                        # fallback: remove leading slash
                        path = path.lstrip('/')
                    # remove leading version if present (eg. v12345/)
                    import re
                    path = re.sub(r'^v\d+/', '', path)
                    # strip extension
                    return path.rsplit('.', 1)[0]

                public_id = extract_public_id(bi_str)

                cfg = settings.CLOUDINARY_BANNER
                cloudinary.config(
                    cloud_name=cfg['CLOUD_NAME'],
                    api_key=cfg['API_KEY'],
                    api_secret=cfg['API_SECRET'],
                )
                try:
                    info = cloudinary_api.resource(public_id)
                    url = info.get('secure_url') or info.get('url')
                    if url and url != bi_str:
                        user.banner_imagen = url
                        changed = True
                        self.stdout.write(f"updated banner for {user.email} -> {url}")
                except Exception as e:
                    self.stderr.write(f"unable to fetch banner url for {bi_str} (public_id {public_id}): {e}")

            if changed:
                user.save(update_fields=['profile_imagen', 'banner_imagen'])
                count += 1

        self.stdout.write(self.style.SUCCESS(f"migration complete, {count} users updated"))
