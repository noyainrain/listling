.. http:post:: /api/(collection-path)/move

   ``{"item_id", "to_id"}``

   Move the item with *item_id* to the position directly after the item with *to_id*.

   If *to_id* is ``null``, move the item to the top of the collection.

   If there is no item with *item_id* or *to_id* in the collection, a :ref:`ValueError`
   (``item_not_found`` or ``to_not_found``) is returned.

   Permission: Authenticated users.
