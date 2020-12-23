.. http:get:: /api/(resource-url)?slice

   Query the collection for a *slice* of items.

   *slice* is a *slice string*. The maximum number of items is limited to a *limit* of 100, i.e.
   *stop* is capped at *start* + *limit*. Defaults to ``:``.

   Example: ``/api/cats`` (which is equivalent to ``/api/cats?slice=:`` or
   ``/api/cats?slice=0:100``) returns the first hundred items and ``/api/cats?slice=10:20`` returns
   the items from index 10 up to including 19.
