# -*- coding: utf-8 -*-
# Copyright © 2007-2018 Red Hat, Inc. and others.
#
# This file is part of Bodhi.
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
"""This test suite contains tests for bodhi.server.__init__."""
import collections
import unittest

from pyramid import authentication, authorization, testing
import mock
import munch

from bodhi import server
from bodhi.server import models
from bodhi.server.config import config
from bodhi.tests.server import base


class TestExceptionFilter(unittest.TestCase):
    """Test the exception_filter() function."""
    @mock.patch('bodhi.server.log.exception')
    def test_exception(self, exception):
        """An Exception should be logged and returned."""
        request_response = OSError('Your money is gone.')

        # The second argument is not used.
        response = server.exception_filter(request_response, None)

        self.assertIs(response, request_response)
        exception.assert_called_once_with(
            "Unhandled exception raised:  OSError('Your money is gone.',)")

    @mock.patch('bodhi.server.log.exception')
    def test_no_exception(self, exception):
        """A non-exception should not be logged and should be returned."""
        request_response = 'Your money is safe with me.'

        # The second argument is not used.
        response = server.exception_filter(request_response, None)

        self.assertIs(response, request_response)
        self.assertEqual(exception.call_count, 0)


class TestGetBuildinfo(unittest.TestCase):
    """Test get_buildinfo()."""
    def test_get_buildinfo(self):
        """get_buildinfo() should return an empty defaultdict."""
        # The argument isn't used, so we'll just pass None.
        bi = server.get_buildinfo(None)

        self.assertTrue(isinstance(bi, collections.defaultdict))
        self.assertEqual(bi, {})
        self.assertEqual(bi['made_up_key'], {})


class TestGetCacheregion(unittest.TestCase):
    """Test get_cacheregion()."""
    @mock.patch.dict('bodhi.server.bodhi_config', {'some': 'config'}, clear=True)
    @mock.patch('bodhi.server.make_region')
    def test_get_cacheregion(self, make_region):
        """Test get_cacheregion."""
        # The argument (request) doesn't get used, so we'll just pass None.
        region = server.get_cacheregion(None)

        make_region.assert_called_once_with()
        self.assertEqual(region, make_region.return_value)
        region.configure_from_config.assert_called_once_with({'some': 'config'}, 'dogpile.cache.')


class TestGetKoji(unittest.TestCase):
    """Test get_koji()."""
    @mock.patch('bodhi.server.buildsys.get_session')
    def test_get_koji(self, get_session):
        """Ensure that get_koji() returns the response from buildsys.get_session()."""
        # The argument is not used, so set it to None.
        k = server.get_koji(None)

        self.assertIs(k, get_session.return_value)


class TestGetReleases(base.BaseTestCase):
    """Test the get_releases() function."""
    def test_get_releases(self):
        """Assert correct return value from get_releases()."""
        request = testing.DummyRequest(user=base.DummyUser('guest'))
        request.db = self.db

        releases = server.get_releases(request)

        self.assertEqual(releases, models.Release.all_releases(self.db))


class TestGetUser(base.BaseTestCase):
    """Test get_user()."""
    def test_authenticated(self):
        """Assert that a munch gets returned for an authenticated user."""
        db_user = models.User.query.filter_by(name=u'guest').one()

        class Request(object):
            """
            Fake a Request.

            We don't use the DummyRequest because it doesn't allow us to set the
            unauthenticated_user attribute. We don't use mock because it causes serialization
            problems with the call to user.__json__().
            """
            cache = mock.MagicMock()
            db = self.db
            registry = mock.MagicMock()
            unauthenticated_userid = db_user.name

        user = server.get_user(Request())

        self.assertEqual(user['groups'], [{'name': 'packager'}])
        self.assertEqual(user['name'], 'guest')
        self.assertTrue(isinstance(user, munch.Munch))

    def test_unauthenticated(self):
        """Assert that None gets returned for an unauthenticated user."""
        class Request(object):
            """
            Fake a Request.

            We don't use the DummyRequest because it doesn't allow us to set the
            unauthenticated_user attribute. We don't use mock because it causes serialization
            problems with the call to user.__json__().
            """
            cache = mock.MagicMock()
            db = self.db
            registry = mock.MagicMock()
            unauthenticated_userid = None

        user = server.get_user(Request())

        self.assertIsNone(user)


class TestGroupfinder(base.BaseTestCase):
    """Test the groupfinder() function."""

    def test_no_user(self):
        """Test when there is not a user."""
        request = testing.DummyRequest(user=base.DummyUser('guest'))
        request.db = self.db

        # The first argument isn't used, so just set it to None.
        groups = server.groupfinder(None, request)

        self.assertEqual(groups, ['group:packager'])

    def test_user(self):
        """Test with a user."""
        request = testing.DummyRequest(user=None)

        # The first argument isn't used, so just set it to None.
        self.assertIsNone(server.groupfinder(None, request))


class TestMain(base.BaseTestCase):
    """
    Assert correct behavior from the main() function.
    """
    @mock.patch('bodhi.server.Configurator.set_authentication_policy')
    @mock.patch('bodhi.server.Configurator.set_authorization_policy')
    def test_authtkt_timeout_defined(self, set_authorization_policy, set_authentication_policy):
        """Ensure that main() uses the setting when authtkt.timeout is defined in settings."""
        with mock.patch.dict(
                self.app_settings,
                {'authtkt.timeout': '10', 'authtkt.secret': 'hunter2', 'authtkt.secure': 'true'}):
            server.main({}, **self.app_settings)

        policy = set_authentication_policy.mock_calls[0][1][0]
        self.assertTrue(isinstance(policy, authentication.AuthTktAuthenticationPolicy))
        self.assertEqual(policy.callback, server.groupfinder)
        self.assertEqual(policy.cookie.hashalg, 'sha512')
        self.assertEqual(policy.cookie.max_age, 10)
        self.assertEqual(policy.cookie.secure, True)
        self.assertEqual(policy.cookie.secret, 'hunter2')
        self.assertEqual(policy.cookie.timeout, 10)
        set_authentication_policy.assert_called_once_with(policy)
        # Ensure that the ACLAuthorizationPolicy was used
        policy = set_authorization_policy.mock_calls[0][1][0]
        self.assertTrue(isinstance(policy, authorization.ACLAuthorizationPolicy))
        set_authorization_policy.assert_called_once_with(policy)

    @mock.patch('bodhi.server.Configurator.set_authentication_policy')
    @mock.patch('bodhi.server.Configurator.set_authorization_policy')
    def test_authtkt_timeout_undefined(self, set_authorization_policy, set_authentication_policy):
        """Ensure that main() uses a default if authtkt.timeout is undefined in settings."""
        with mock.patch.dict(
                self.app_settings, {'authtkt.secret': 'hunter2', 'authtkt.secure': 'true'}):
            server.main({}, **self.app_settings)

        policy = set_authentication_policy.mock_calls[0][1][0]
        self.assertTrue(isinstance(policy, authentication.AuthTktAuthenticationPolicy))
        self.assertEqual(policy.callback, server.groupfinder)
        self.assertEqual(policy.cookie.hashalg, 'sha512')
        self.assertEqual(policy.cookie.max_age, 86400)
        self.assertEqual(policy.cookie.secure, True)
        self.assertEqual(policy.cookie.secret, 'hunter2')
        self.assertEqual(policy.cookie.timeout, 86400)
        set_authentication_policy.assert_called_once_with(policy)
        # Ensure that the ACLAuthorizationPolicy was used
        policy = set_authorization_policy.mock_calls[0][1][0]
        self.assertTrue(isinstance(policy, authorization.ACLAuthorizationPolicy))
        set_authorization_policy.assert_called_once_with(policy)

    @mock.patch('bodhi.server.bugs.set_bugtracker')
    def test_calls_set_bugtracker(self, set_bugtracker):
        """
        Ensure that main() calls set_bugtracker().
        """
        server.main({}, testing='guest', session=self.db, **self.app_settings)

        set_bugtracker.assert_called_once_with()

    @mock.patch.dict('bodhi.server.config.config', {'test': 'changeme'})
    def test_settings(self):
        """Ensure that passed settings make their way into the Bodhi config."""
        self.app_settings.update({'test': 'setting'})

        server.main({}, testing='guest', session=self.db, **self.app_settings)

        self.assertEqual(config['test'], 'setting')


class TestGetDbSessionForRequest(unittest.TestCase):
    """Test the get_db_session_for_request() function."""

    def test_cleanup_exception(self):
        """Test cleanup() when there is an Exception."""
        request = mock.Mock()
        session = server.get_db_session_for_request(request)
        cleanup = request.add_finished_callback.mock_calls[0][1][0]
        request.exception = IOError('The Internet ran out of cats.')

        cleanup(request)

        # Since there was an Exception, the session should have been rolled back and closed.
        self.assertEqual(session.rollback.mock_calls, [mock.call()])
        self.assertEqual(session.commit.mock_calls, [])
        self.assertEqual(session.close.mock_calls, [mock.call()])

    def test_cleanup_no_exception(self):
        """Test cleanup() when there is not an Exception."""
        request = mock.Mock()
        session = server.get_db_session_for_request(request)
        cleanup = request.add_finished_callback.mock_calls[0][1][0]
        request.exception = None

        cleanup(request)

        # Since there was no Exception, the session should have been committed and closed.
        self.assertEqual(session.rollback.mock_calls, [])
        self.assertEqual(session.commit.mock_calls, [mock.call()])
        self.assertEqual(session.close.mock_calls, [mock.call()])

    def test_session_from_registry_sessionmaker(self):
        """Assert the session is created using the sessionmaker in the registry."""
        mock_request = mock.Mock()
        session = server.get_db_session_for_request(mock_request)
        mock_request.registry.sessionmaker.assert_called_once_with()
        self.assertEqual(session, mock_request.registry.sessionmaker.return_value)
