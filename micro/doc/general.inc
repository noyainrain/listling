Introduction
------------

The application provides a JSON REST API.

Arguments are passed to an endpoint simply as JSON object and the result is returned as JSON value.
*Objects* contain a ``__type__`` attribute that holds the name of the object type.

If a requested endpoint doesn't exist, a :ref:`NotFoundError` is returned. For any endpoint, an
:ref:`InputError` is returned if the input contains invalid arguments. A :ref:`RateLimitError` is
returned if the current client exceeds the allowed rate limit for an operation.

The URL that uniquely identifies an object is referred to as *object-url*, e.g. ``users/abc`` for a
:ref:`User` with the *id* ``abc``.

Authentication and Permissions
------------------------------

To make an API request authenticated as some user, include a cookie named ``auth_secret`` with the
:ref:`User` 's *auth_secret*.

If user authentication with the given secret fails, an :ref:`AuthenticationError` is returned. For
any endpoint, a :ref:`PermissionError` is returned if the current user is not allowed to perform the
action.

Additional types
----------------

A *slice* represents a range of a list, as array ``[start, stop]``, from index *start* (inclusive)
to *stop* (exclusive). Both *start* and *stop* may be ``null``, referring to the beginning (0) and
end (list length) of the list respectively.

A *slice string* has the form ``{start}:{stop}``. Both *start* and *stop* may be omitted, meaning
``null``.

A *polyglot string* is an :class:`Object` holding multiple translations of a string indexed by short
language tag.

*Markup text* is a string that may contain the following markup:

* ``*Emphasized text*``
* ``**Important text**``
* ``* List item``

Usage examples
--------------

A new :ref:`User` is created and logged in with the following request::

    $ curl -d "" https://example.org/api/login
    {
        "__type__": "User",
        "id": "abcd",
        "auth_secret": "wxyz",
        ...
    }

To authenticate further API calls, the returned *auth_secret* is set as cookie.

Setting a user's *email* address requires multiple steps. First::

    $ curl -b "auth_secret=wxyz" -d '{"email": "happy@example.org"}' \
           https://example.org/api/users/abcd/set-email
    {
        "__type__": "AuthRequest",
        "id": "efgh"
    }

This triggers a third party authentication via the email provider (as layed out in
:ref:`AuthRequest`). The resulting authentication code (here ``stuv``) is then verified to finish
setting the email address::

    $ curl -b "auth_secret=wxyz" -d '{"auth_request_id": "efgh", "auth": "stuv"}' \
           https://example.org/api/users/abcd/finish-set-email
    {
        "__type__": "User",
        "id": "abcd",
        "email": "happy@example.org",
        ...
    }

.. _Gone:

Gone
----

Former object that does not exist anymore.

.. _Collection:

Collection
----------

Collection of objects.

.. include:: micro/collection-attributes.inc

.. include:: micro/collection-endpoints.inc

.. _Device:

Device
------

:ref:`User` device.

.. describe:: auth_secret

   Secret for authentication.

.. describe:: authenticate_time

   Time the device last authenticated.

.. describe:: notification_status

   Notification status:

   * ``on``: Notifications are enabled
   * ``off``: Notifications are disabled
   * ``off.expired``: Notifications are disabled because *push_subscription* expired

.. describe:: push_subscription

   Push subscription token used for sending notifications. May be ``null``.

.. describe:: user_id

   ID of the :ref:`User` the device belongs to.

.. describe:: user

   :ref:`User` the device belongs to.

.. _Devices:

Devices
-------

.. http:post:: /api/devices

   Create and sign in a new :ref:`User`. A :ref:`Device` is registered for the user and
   returned.

   The very first user who signs in is granted staff membership.

.. http:get:: /api/devices/(id)

   Get the :ref:`Device` with *id*.

   ``self`` refers to the authenticated user device.

   Permission: Device owner.

.. http:patch:: /api/devices/(id)

   ``{"op": "enable_notifications", "push_subscription"}``

   Enable notifications for the device, using *push_subscription*.

   A confirmation message is sent to the device. If there is a communication issue, a
   :ref:`CommunicationError` is returned.

   Permission: Device owner.

   ``{"op": "disable_notifications"}``

   Disable notifications for the device.

   Permission: Device owner.

.. _AuthRequest:

AuthRequest
-----------

Third party authentication request.

To set an :ref:`User` 's email address, a third party authentication via the email provider is
performed to proof ownership over the address: First an email message containing a secret
authentication code is sent to the user. The email provider authenticates the user by login to their
mailbox, where they retrieve the code. Finally the code is passed back to and verified by the
application.

.. include:: micro/object-attributes.inc

.. _Activity:

Activity
--------

Activity feed (of events) around a common topic/context.

*activity-url* is the URL that identifies the activity feed, e.g. ``/api/activity``.

.. describe:: user_subscribed

   Indicates if the user subscribed to the feed.

.. describe:: items

   List of recorded :ref:`Event` s.

.. http:patch:: /api/(activity-url)

   ``{"op": "subscribe"}``

   Subscribe the user to the feed.

   Permission: Authenticated users.

   ``{"op": "unsubscribe"}``

   Unsubscribe the user from the feed.

   Permission: Authenticated users.

.. http:get:: /api/(activity-url)/stream

   Get a live stream of :ref:`Event` s as ``text/event-stream``.

.. _Event:

Event
-----

Event about an action on an *object* by an *user*.

.. include:: micro/object-attributes.inc

.. describe:: type

   Type of the event.

.. describe:: object

   Object for which the event happened. :ref:`Gone` if the object does not exist anymore. ``null``
   if the event is global.

.. describe:: user

   :ref:`User` who triggered the event.

.. describe:: time

   Date and time at which the event happened.

.. describe:: detail

   Dictionary with additonal details about the event. The contents depend on the event *type*.

.. _Location:

Location
--------

Location.

.. describe:: name

   Name of the location.

.. describe:: coords

   Coordinates as latitude-longitude pair. May be ``null``.

Resources
---------

.. _Resource:

Resource
^^^^^^^^

Web resource description.

.. include:: micro/resource-attributes.inc

.. _Image:

Image
^^^^^

Image :ref:`Resource` description.

Note that the *image* representation is always ``null``.

.. include:: micro/resource-attributes.inc

.. _Video:

Video
^^^^^

Video :ref:`Resource` description.

.. include:: micro/resource-attributes.inc

Previews
^^^^^^^^

Web :ref:`Resource` previews.

.. http:get:: /api/previews/(url)

   Get a description of the web :ref:`Resource` at *url*.

Analytics
---------

.. _Statistic:

Statistic
^^^^^^^^^

Statistic about a topic over time.

.. http:get:: /api/analytics/statistics/(topic)

   Query the collection.

   The query result is an object ``{items}`` holding an array of queried *items*.

   Available topics are:

   * ``users``: Count of all users
   * ``users-actual``: Count of actual users, i.e. who returned at least once after the first day
   * ``users-active``: Count of monthly active users, i.e. who were seen in the last 30 days

   Permission: Staff members.

.. _Point:

Point
^^^^^

Statistic data point.

.. describe:: t

   Time the statistic was collected.

.. describe:: v

   Statistic value.

.. _Referral:

Referral
^^^^^^^^

Referral from another site.

.. include:: micro/object-attributes.inc

.. describe:: url

   Absolute referrer URL.

.. describe:: time

   Date and time of the referral.

.. _Referrals:

Referrals
^^^^^^^^^

:ref:`Referral` :ref:`Collection`, latest first.

Only staff members can query the referrals.

.. include:: micro/collection-endpoints.inc

.. http:post:: /api/analytics/referrals

   ``{url}``

   Record a :ref:`Referral` from *url* and return it.

.. http:get:: /api/analytics/referrals/summary?period

   Get a referral summary for the given time *period*.

   *period* is a simple ISO 8601 time interval string and defaults to the last 7 days.

   The summary is an object ``{referrers}``, where *referrers* is a sorted array of objects
   ``{url, count}`` with the referrer *url* and *count* of occurrences.

   Permission: Staff members.

Files
-----

To upload a file, ``POST`` to ``/files``. Supported file types are ``image/bmp``, ``image/gif``,
``image/jpeg``, ``image/png`` and ``image/svg+xml``.

Errors
------

.. _ValueError:

ValueError
^^^^^^^^^^

Returned for value-related errors.

.. _InputError:

InputError
^^^^^^^^^^

Returned if the input to an endpoint contains one or more arguments with an invalid value.

InputError is a :ref:`ValueError` with *code* set to ``input_invalid``.

.. describe:: errors

   Map of argument names / error strings for every problematic argument of the input.

.. _NotFoundError:

NotFoundError
^^^^^^^^^^^^^

Returned if a requested endpoint does not exist.

.. _AuthenticationError:

AuthenticationError
^^^^^^^^^^^^^^^^^^^

Returned if user authentication fails.

.. _PermissionError:

PermissionError
^^^^^^^^^^^^^^^

Returned if the current user is not allowed to perform an action.

.. _RateLimitError:

RateLimitError
^^^^^^^^^^^^^^

Returned if the current client exceeds the allowed rate limit for an operation.

.. _CommunicationError:

CommunicationError
^^^^^^^^^^^^^^^^^^

Returned if communication with a third party fails.

.. _AnalysisError:

AnalysisError
^^^^^^^^^^^^^

Returned if analyzing a web resource fails.

.. _NoResourceError:

NoResourceError
^^^^^^^^^^^^^^^

:ref:`AnalysisError` returned if there is no resource at the URL to analyze.

.. _ForbiddenResourceError:

ForbiddenResourceError
^^^^^^^^^^^^^^^^^^^^^^

:ref:`AnalysisError` returned if access to the resource subject to analysis is forbidden.

.. _BorkenResourceError:

BrokenResourceError
^^^^^^^^^^^^^^^^^^^

:ref:`AnalysisError` returned if the resource subject to analysis is broken.
