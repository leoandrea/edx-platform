""" Management command to back-populate marketing emails opt-in for the user accounts. """

import time

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from common.djangoapps.student.models import UserAttribute
from common.djangoapps.util.query import use_read_replica_if_available

OLD_USER_ATTRIBUTE_NAME = 'marketing_emails_opt_in'
NEW_USER_ATTRIBUTE_NAME = 'is_marketable'


class Command(BaseCommand):
    """
    Example usage:
        $ ./manage.py lms populate_is_marketable_user_attribute
    """
    help = """
        Creates a row in the UserAttribute table for all users in the platform.
        This command back-populates the 'is_marketable' attribute in the
        UserAttribute table for the user accounts.
        """

    def add_arguments(self, parser):
        parser.add_argument(
            '--batch-delay',
            type=float,
            dest='batch_delay',
            default=0.5,
            help='Time delay in each iteration'
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            dest='batch_size',
            default=5000,
            help='Batch size'
        )

    def _get_user_attribute_queryset(self, user_attribute_id, batch_size):
        """ Fetches the user attributes in batches """
        self.stdout.write(
            f'Fetching user attributes in batch starting from ID {user_attribute_id} with batch size {batch_size}'
        )
        query_set = UserAttribute.objects.filter(
            id__gte=user_attribute_id,
            name=OLD_USER_ATTRIBUTE_NAME
        ).order_by('id')[:batch_size]
        return use_read_replica_if_available(query_set)

    def _get_user_queryset(self, offset, batch_size):
        """ Fetches the users in batches """
        self.stdout.write(f'Fetching users in batch from {offset} to {offset + batch_size}')
        query_set = get_user_model().objects.order_by('id')[offset: offset + batch_size]
        return use_read_replica_if_available(query_set)

    def _backfill_is_marketable_user_attribute(self, batch_size, batch_delay):
        """ Backfills the is_marketable user attribute """
        offset = 0
        user_query_set = use_read_replica_if_available(get_user_model().objects)
        count = user_query_set.count()

        while offset < count:
            users = self._get_user_queryset(offset, batch_size)
            for user in users:
                if not UserAttribute.get_user_attribute(user, NEW_USER_ATTRIBUTE_NAME):
                    UserAttribute.set_user_attribute(user, NEW_USER_ATTRIBUTE_NAME, str(user.is_active).lower())
            offset += batch_size
            time.sleep(batch_delay)

    def _rename_user_attribute_name(self, batch_size, batch_delay):
        """ Renames the old user attribute 'marketing_emails_opt_in' to 'is_marketable' """
        last_user_attribute_id = 1
        user_attributes = self._get_user_attribute_queryset(last_user_attribute_id, batch_size)

        while user_attributes:
            updates = []
            for user_attribute in user_attributes:
                user_attribute.name = NEW_USER_ATTRIBUTE_NAME
                last_user_attribute_id = user_attribute.id
                updates.append(user_attribute)

            UserAttribute.objects.bulk_update(updates, ['name'])
            time.sleep(batch_delay)
            user_attributes = self._get_user_attribute_queryset(last_user_attribute_id, batch_size)

    def handle(self, *args, **options):
        """
        This command back-populates the 'is_marketable' attribute for all existing users who do not already
        have the attribute set.
        """
        batch_delay = options['batch_delay']
        batch_size = options['batch_size']
        self.stdout.write(f'Command execution started with options: {options}.')

        self._rename_user_attribute_name(batch_size, batch_delay)
        self._backfill_is_marketable_user_attribute(batch_size, batch_delay)

        self.stdout.write('Command executed successfully.')
