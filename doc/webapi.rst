Web API
=======

.. include:: micro/general.inc

.. _Listling:

Listling
--------

Listling application.

.. include:: micro/application-endpoints.inc

.. _User:

User
----

Listling user.

.. include:: micro/user-attributes.inc

.. describe:: lists

   :ref:`UserLists` of the user.

.. _Users:

Users
-----

.. include:: micro/user-endpoints.inc

.. include:: micro/user-devices.inc

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

.. _Lists:

Lists
-----

.. http:post:: /api/lists

   ``{"use_case": "simple"}``

   Create a :ref:`List` for the given *use_case* and return it.

   Available *use_case* s are ``simple``, ``todo``, ``poll``, ``shopping``, ``meeting-agenda``,
   ``playlist`` and ``map``.

   Permission: Authenticated users.

.. http:post:: /api/lists/create-example

   ``{"use_case"}``

   Create an example :ref:`List` for the given *use_case* and return it.

   For available *use_cases* see :http:post:`/api/lists`, excluding ``simple``.

   Permission: Authenticated users.

.. http:get:: /api/lists/(id)

   Get the :ref:`List` given by *id*.

.. _List:

List
----

.. include:: micro/object-attributes.inc

.. include:: micro/editable-attributes.inc

.. describe:: title

   Title of the list.

.. describe:: description

   Description of the list as *markup text*. May be ``null``.

.. describe:: order

   Key by which items are ordered. Available keys are ``title``. May be ``null``.

.. describe:: features

   Set of features enabled for the list.

   Available features are ``check``, ``assign``, ``vote``, ``value``, ``time``, ``location`` and
   ``play``.

.. describe:: assign_by_default

   Indicates if the author is assigned to new items by default.

.. describe:: value_unit

   Unit of :ref:`Item` *value* s. May be ``null``.

.. describe:: mode

   List mode, describing how users work with the list. In ``collaborate`` mode, users collaborate on
   the list. In ``view`` mode, users only view the list.

   The following permissions apply:

   * ``collaborate``: Authenticated users may modify [1]_ the list and modify [2]_ items
   * ``view``: None

   List owners always have full permissions.

   .. [1] Edit the list and create and move items
   .. [2] Edit, trash, restore, check, uncheck, assign to and unassign from items

.. describe:: item_template

   Template for *text* content of new items as *markup text*. May be ``null``.

.. describe:: value_summary_ids

   Summary table for :ref:`Item` *value* s, referencing :ref:`User` s by *id*. See *value_summary*.

.. describe:: value_summary

   Summary table for :ref:`Item` *value* s.

   If *features* ``value`` is enabled, ``total`` holds the sum over all items.

   Additionally, if *features* ``assign`` is enabled, the share of each assigned :ref:`User` is
   included. If an item has multiple assignees, its value is split equally between them.

.. describe:: owners

   List :ref:`ListOwners`.

.. describe:: items

   List :ref:`ListItems`.

.. describe:: activity

   List :ref:`Activity` feed.

.. include:: micro/editable-endpoints.inc

Events:

.. describe:: item-assignees-assign

   Published when a :ref:`User` *assignee* has been assigned to an item.

.. describe:: item-assignees-unassign

   Published when a :ref:`User` *assignee* has been unassigned from an item.

.. describe:: item-votes-vote

   Published when an item has been voted for.

.. describe:: item-votes-unvote

   Published when an item has been unvoted.

.. _ListOwners:

Owners
^^^^^^

:ref:`Collection` of :ref:`User` s who hold ownership of an object.

The object has at least one owner.

Events:

.. describe:: object-owners-grant

   Published when ownership of the object has been granted to a user.

.. describe:: object-owners-revoke

   Published when ownership of the object has been revoked from a user.

.. include:: micro/collection-endpoints.inc

*user_owner* indicates if the user is owner of the object.

.. http:post:: /api/(owners-url)

   ``{user_id}``

   Grant ownership of the object to the :ref:`User` with *user_id*.

   Permission: Object owners.

.. http:delete:: /api/(owners-url)/(id)

   Revoke ownership of the object from the :ref:`User` with *id*.

   Permission: Object owners.

OwnersEvent
"""""""""""

:ref:`Event` related to Owners.

.. describe:: owner_id

   ID of the affected :ref:`User`.

.. describe:: owner

   Affected :ref:`User`.

.. _ListUsers:

Users
^^^^^

.. http:get:: /api/lists/(id)/users?name=

   Query users who interacted with the list and (partially) match *name*.

   A maximum of 10 items is returned.

.. _ListItems:

Items
^^^^^

List :ref:`Item` s in :ref:`List` *order*.

.. include:: micro/collection-endpoints.inc

.. http:post:: /api/lists/(id)/items

   ``{"title", "text": null, "resource": null, "value": null, "location": null}``

   Create an :ref:`Item` and return it.

   Permission: Authenticated users.

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

   Title of the item as *markup text*.

.. describe:: value

   Decimal value associated with the item. May be ``null``.

.. describe:: time

   *datetime* or *date* of the item. May be ``null``.

.. describe:: location

   :ref:`Location` of the item. May be ``null``.

.. describe:: checked

   Indicates if the item is marked as complete.

.. describe:: assignees

   Item :ref:`ItemAssignees`.

.. describe:: votes

   :ref:`ItemVotes` for the item.

.. _Items:

Items
-----

.. http:get:: /api/items/(id)

.. http:get:: /api/lists/(list-id)/items/(id)

   Get the :ref:`Item` given by *id*.

   .. deprecated:: 0.39.0

      Nested URL.

.. include:: micro/editable-endpoints.inc

.. include:: micro/trashable-endpoints.inc

.. http:post:: /api/items/(id)/check

.. http:post:: /api/lists/(list-id)/items/(id)/check

   Mark the item as complete.

   If the feature ``check`` is not enabled for the list, a :ref:`ValueError` (`feature_disabled`) is
   returned.

   Permission: Authenticated users.

   .. deprecated:: 0.39.0

      Nested URL.

.. http:post:: /api/items/(id)/uncheck

.. http:post:: /api/lists/(list-id)/items/(id)/uncheck

   Mark the item as incomplete.

   If the feature ``check`` is not enabled for the list, a :ref:`ValueError` (`feature_disabled`) is
   returned.

   Permission: Authenticated users.

   .. deprecated:: 0.39.0

      Nested URL.

.. _ItemAssignees:

Assignees
^^^^^^^^^

:ref:`Collection` of :ref:`User` s assigned to the item.

.. include:: micro/collection-endpoints.inc

.. http:post:: /api/items/(id)/assignees

.. http:post:: /api/lists/(list-id)/items/(id)/assignees

   ``{assignee_id}``

   Assign the :ref:`User` with *assignee_id* to the item.

   If :ref:`List` *features* ``assign`` is disabled, if there is no user with
   *assignee_id* or if the user is already assigned, a :ref:`ValueError` is returned.

   Permission: See :ref:`List` *mode*.

   .. deprecated:: 0.39.0

      Nested URL.

.. http:delete:: /api/items/(id)/assignees/(assignee-id)

.. http:delete:: /api/lists/(list-id)/items/(id)/assignees/(assignee-id)

   Unassign the :ref:`User` with *assignee-id* from the item.

   If :ref:`List` *features* ``assign`` is disabled, a :ref:`ValueError` is returned.

   Permission: See :ref:`List` *mode*. Authenticated users may unassign themselves.

   .. deprecated:: 0.39.0

      Nested URL.

.. _ItemVotes:

Votes
^^^^^

:ref:`Collection` of :ref:`User` s who voted for the item, latest first.

.. describe:: user_voted

   Indicates if the user voted for the item.

.. include:: micro/collection-endpoints.inc

.. http:post:: /api/items/(id)/votes

.. http:post:: /api/lists/(list-id)/items/(id)/votes

   Vote for the item.

   Permission: Authenticated users.

   .. deprecated:: 0.39.0

      Nested URL.

.. http:delete:: /api/items/(id)/votes/user

.. http:delete:: /api/lists/(list-id)/items/(id)/votes/user

   Unvote the item, i.e. annul a previous vote.

   Permission: Authenticated users.

   .. deprecated:: 0.39.0

      Nested URL.
