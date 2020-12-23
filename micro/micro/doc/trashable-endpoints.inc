.. http:post:: /api/(object-url)/trash

   Trash the object.

   If the object is already trashed, nothing happens. A trashed object is permanently deleted after
   7 days.

   Permission: Authenticated users.

.. http:post:: /api/(object-url)/restore

   Restore the previously trashed object.

   If the object is not trashed, nothing happens.

   Permission: Authenticated users.
