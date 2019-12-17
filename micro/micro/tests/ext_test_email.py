# micro
# Copyright (C) 2018 micro contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU
# Lesser General Public License as published by the Free Software Foundation, either version 3 of
# the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without
# even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License along with this program.
# If not, see <http://www.gnu.org/licenses/>.

# pylint: disable=missing-docstring; test module

import asyncore
from smtpd import SMTPServer
from threading import Thread
from warnings import catch_warnings

from micro import EmailError
from micro.tests.test_micro import MicroTestCase

class EmailTest(MicroTestCase):
    def setUp(self):
        super().setUp()
        self.app.smtp_url = '//localhost:52525'
        # NOTE: Omitting decode_data triggers a warning in Python 3.5, which we can safely ignore
        # because we do not touch data
        with catch_warnings(record=True):
            self.smtpd = DiscardingSMTPServer(('localhost', 52525), None)
        # NOTE: asyncore is deprecated, but needed for smtpd, which is not (yet). aiosmtpd may be
        # added to the standard library as replacement.
        self.thread = Thread(target=asyncore.loop, kwargs={'timeout': 0.1})
        self.thread.start()

    def tearDown(self):
        super().tearDown()
        self.smtpd.close()
        self.thread.join()

    def test_user_store_email(self):
        self.user.store_email('happy@example.org')
        self.assertEqual(self.user.email, 'happy@example.org')

    def test_user_store_email_email_duplicate(self):
        self.staff_member.store_email('happy@example.org')
        with self.assertRaisesRegex(ValueError, 'email_duplicate'):
            self.user.store_email('happy@example.org')

    def test_user_store_email_email_same(self):
        self.user.store_email('happy@example.org')
        self.user.store_email('happy@example.org')
        self.assertEqual(self.user.email, 'happy@example.org')

    def test_user_store_email_email_removed(self):
        self.user.store_email('happy@example.org')
        self.user.remove_email()
        self.user.store_email('happy@example.org')
        self.assertEqual(self.user.email, 'happy@example.org')

    def test_user_store_email_email_overwritten(self):
        self.user.store_email('happy@example.org')
        self.user.store_email('grumpy@example.org')
        self.user.store_email('happy@example.org')
        self.assertEqual(self.user.email, 'happy@example.org')

    def test_user_set_email(self):
        code = None
        def _render_email_auth_message(email, auth_request, auth):
            # pylint: disable=unused-argument; part of the API
            nonlocal code
            code = auth
            return 'Subject: Important\n\nMeow!\n'
        self.app.render_email_auth_message = _render_email_auth_message

        auth_request = self.user.set_email('happy@example.org')
        self.user.finish_set_email(auth_request, code)
        self.assertEqual(self.user.email, 'happy@example.org')

    def test_user_set_email_auth_invalid(self):
        auth_request = self.user.set_email('happy@example.org')
        with self.assertRaisesRegex(ValueError, 'auth_invalid'):
            self.user.finish_set_email(auth_request, 'foo')

    def test_user_remove_email(self):
        self.user.store_email('happy@example.org')
        self.user.remove_email()
        self.assertIsNone(self.user.email)

    def test_user_remove_email_user_no_email(self):
        with self.assertRaisesRegex(ValueError, 'user_no_email'):
            self.user.remove_email()

    def test_user_send_email(self):
        self.user.store_email('happy@example.org')
        self.user.send_email('Subject: Important\n\nMeow!\n')

    def test_user_send_email_msg_invalid(self):
        self.user.store_email('happy@example.org')
        with self.assertRaisesRegex(ValueError, 'msg_invalid'):
            self.user.send_email('foo')

    def test_user_send_email_user_no_email(self):
        with self.assertRaisesRegex(ValueError, 'user_no_email'):
            self.user.send_email('Subject: Important\n\nMeow!\n')

    def test_user_send_email_no_smtpd(self):
        self.user.store_email('happy@example.org')
        self.app.smtp_url = '//localhoax'
        with self.assertRaises(EmailError):
            self.user.send_email('Subject: Important\n\nMeow!\n')

class DiscardingSMTPServer(SMTPServer):
    def process_message(self, peer, mailfrom, rcpttos, data, **kwargs):
        # pylint: disable=arguments-differ; kwargs not available in Python < 3.5
        pass
