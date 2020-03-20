.. http:get:: /api/users/(id)

   Get the user given by *id*.

.. include:: micro/editable-endpoints.inc

.. http:post:: /api/users/(id)/set-email

   {"email"}

   Start to set the user's *email* address.

   A third party authentication via the email provider (as layed out in :ref:`AuthRequest`) is
   triggered and a corresponding :ref:`AuthRequest` is returned. To finish setting the email address
   use :http:post:`/api/users/(id)/finish-set-email`.

   Permission: The user oneself.

.. http:post:: /api/users/(id)/finish-set-email

   {"auth_request_id", "auth"}

   Finish setting the user's *email* address and return the user.

   *auth* is the authentication code, resulting from the :ref:`AuthRequest` with *auth_request_id*,
   to be verified. If the verification fails, a :ref:`ValueError` (``auth_invalid``) is returned. If
   the given email address is already associated with another user, a :ref:`ValueError`
   (``email_duplicate``) is returned.

   Permission: The user oneself.

.. http:post:: /api/users/(id)/remove-email

   Remove the user's current *email* address and return the user.

   If the user's *email* is not set, a :ref:`ValueError` (``user_no_email``) is returned.

   Permission: The user oneself.

.. http:patch:: /api/users/(id)

   ``{"op": "enable_device_notifications", "push_subscription"}``

   Enable device notifications, using *push_subscription*.

   A confirmation message is sent to the device. If there is a communication issue, a
   :ref:`CommunicationError` is returned.

   Permission: The user oneself.

   ``{"op": "disable_device_notifications"}``

   Disable device notifications.

   Permission: The user oneself.
