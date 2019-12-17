.. http:post:: /api/(object-url)

   ``{attrs...}``

   Edit the attributes given by *attrs* and return the updated object.

   A *trashed* (deleted) object cannot be edited. In this case a :ref:`ValueError`
   (`object_trashed`) is returned.

   Permission: Authenticated users.
