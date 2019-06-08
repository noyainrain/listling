Web API
=======

.. include:: micro/general.inc

.. _Listling:

Listling
--------

Listling application.

.. include:: micro/application-endpoints.inc

.. _Lists:

Lists
^^^^^

.. http:post:: /api/lists

   ``{"use_case", "v"}``

   Create a :ref:`List` for the given *use_case* and return it.

   Available *use_case* s are ``simple``, ``todo``, ``shopping``, ``meeting-agenda`` and ``map``.
   The endpoint version *v* must be ``2``.

   Permission: Authenticated users.

   .. deprecated:: 0.3.0

      The signature ``{"title", "description": null, "v": 1}``. Instead, set *use_case* to
      ``simple`` and edit the new list to set *title* and *description*.

.. http:post:: /api/lists/create-example

   ``{"use_case"}``

   Create an example :ref:`List` for the given *use_case* and return it.

   For available *use_cases* see :http:post:`/api/lists`, excluding ``simple``.

   Permission: Authenticated users.

.. http:get:: /api/lists/(id)

   Get the :ref:`List` given by *id*.

.. _User:

User
----

Listling user.

.. include:: micro/user-attributes.inc

.. describe:: lists

   :ref:`UserLists` of the user.

.. include:: micro/user-endpoints.inc

.. _UserLists:

Lists
^^^^^

:ref:`List` :ref:`Collection` of the user, ordered by time added, latest first.

Lists created by the user are added automatically.

.. include:: micro/collection-attributes.inc

.. include:: micro/collection-endpoints.inc

.. http:post:: /users/(id)/lists

   ``{"list_id"}``

   Add the list with *list_id*.

   If the list is already in the collection, the associated time is updated. If there is no list
   with *list_id*, a :ref:`ValueError` is returned.

   Permission: The user oneself.

.. http:delete:: /users/(id)/lists/(list-id)

   Remove the list with *list-id*.

   If the user is the list owner, a :ref:`ValueError` is returned.

   Permission: The user oneself.

.. _Settings:

Settings
--------

App settings.

.. include:: micro/settings-attributes.inc

.. include:: micro/settings-endpoints.inc

.. _List:

List
----

.. include:: micro/object-attributes.inc

.. include:: micro/editable-attributes.inc

.. describe:: title

   Title of the list.

.. describe:: description

   Description of the list. May be ``null``.

.. describe:: features

   Set of features enabled for the list.

   Available features are ``check`` and ``location``.

.. describe:: mode

   List mode, describing how users work with the list. In ``collaborate`` mode, users collaborate on
   the list. In ``view`` mode, users only view the list.

   The following permissions apply:

   * ``collaborate``: Authenticated users may modify [1]_ the list and modify [2]_ items
   * ``view``: None

   List owners always have full permissions.

   .. [1] Edit the list and create and move items
   .. [2] Edit, trash, restore, check and uncheck items

.. describe:: items

   List :ref:`Items`.

.. include:: micro/editable-endpoints.inc

.. _Items:

Items
^^^^^

.. http:get:: /api/lists/(id)/items

   Get all :ref:`Item` s of the list.

.. http:post:: /api/lists/(id)/items

   ``{"title", "text": null, "location": null}``

   Create an :ref:`Item` and return it.

   Permission: Authenticated users.

.. http:get:: /api/lists/(id)/items/(item-id)

   Get the :ref:`Item` given by *item-id*.

.. include:: micro/orderable-endpoints.inc

.. _Item:

Item
----

.. include:: micro/object-attributes.inc

.. include:: micro/editable-attributes.inc

.. include:: micro/trashable-attributes.inc

.. include:: micro/with-content-attributes.inc

.. describe:: list_id

   ID of the list the item belongs to.

.. describe:: title

   Title of item.

.. describe:: location

   :ref:`Location` of the item. May be ``null``.

.. describe:: checked

   Indicates if the item is marked as complete.

.. include:: micro/editable-endpoints.inc

.. include:: micro/trashable-endpoints.inc

.. http:post:: /api/lists/(list-id)/items/(id)/check

   Mark the item as complete.

   If the feature ``check`` is not enabled for the list, a :ref:`ValueError` (`feature_disabled`) is
   returned.

   Permission: Authenticated users.

.. http:post:: /api/lists/(list-id)/items/(id)/uncheck

   Mark the item as incomplete.

   If the feature ``check`` is not enabled for the list, a :ref:`ValueError` (`feature_disabled`) is
   returned.

   Permission: Authenticated users.
