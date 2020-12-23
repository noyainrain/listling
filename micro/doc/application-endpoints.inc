.. http:get:: /api/settings

   Get the settings.

.. http:get:: /api/activity

   Global :ref:`Activity` feed.

.. http:get:: /api/activity/v2

   Global :ref:`Activity` feed.

   .. deprecated:: 0.57.0

      Use :http:get:`/api/activity` instead.

.. http:post:: /api/login

   ``{"code": null}``

   Log in an :ref:`User` (device) and return them.

   If *code* is given, log in an existing user with the login *code*. If the login fails, a
   :exc:`ValueError` (``code_invalid``) is returned.

   If *code* is ``null``, create and log in a new user. The very first user who logs in is
   registered as staff member.

   .. deprecated:: 0.58.0
