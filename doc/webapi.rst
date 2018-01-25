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

   ``{"title", "description": null}``

   Create a :ref:`List` and return it.

   Permission: Authenticated users.

.. http:post:: /api/lists/create-example

   ``{"use_case"}``

   Create an example :ref:`List` for the given *use_case* and return it.

   Available *use_case* s are: ``shopping``, ``meeting-agenda``

   Permission: Authenticated users.

.. http:get:: /api/lists/(id)

   Get the :ref:`List` given by *id*.

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

.. include:: micro/editable-endpoints.inc

.. _Items:

Items
^^^^^

.. http:get:: /api/lists/(id)/items

   Get all :ref:`Item` s of the list.

.. http:post:: /api/lists/(id)/items

   ``{"title", "text": null}``

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

.. describe:: list_id

   ID of the list the item belongs to.

.. describe:: title

   Title of item.

.. describe:: text

   Text content of the item. May be ``null``.

.. include:: micro/editable-endpoints.inc

.. include:: micro/trashable-endpoints.inc
