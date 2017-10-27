* OQ shift issue?: lohnt sich micro-shift implementierung?
  <micro-shift>
    <p class="micro-view-hidden">Trash <button data-shift="visible"></p>
    <div class="micro-view-visible">
      <h1>Trashed <button data-shift="hidden"></h1>
      <ul>...</ul>
    </div>
  </micro-shift>

  <div>
    <p data-visible="not showTrash">Trash <button></p>
    <div data-visible="showTrash">
      <h1>Trashed <button></h1>
      <ul>...</ul>
    </div>
  </div>
  //
  this.querySelector(".show-trash").run = () => this.data.showTrash = true;
  this.querySelector(".hide-trash").run = () => this.data.showTrash = false;

  <div data-class-listling-list-trash-visible="showTrash">
    <p class="listling-list-view-trash-hidden">Trash <button></p>
    <div class="listling-list-view-trash-visible">
      <h1>Trashed <button></h1>
      <ul>...</ul>
    </div>
  </div>
  <style>
    x.listling-list-trash-visible .listling-list-view-trash-hidden {
        display: none;
    }
    x:not(.listling-list-trash-visible) .listling-list-view-trash-visible {
        display: none;
    }
  </style>
  //
  this.querySelector(".show-trash").run = () => this.data.showTrash = true;
  this.querySelector(".hide-trash").run = () => this.data.showTrash = false;

<footer style="text-align: center;">
	<p><small>Made with <span class="fa fa-heart"></span> in Berlin</small></p>
</footer>

think-big-design
* OQ: move-handle / item-number style and padding left/right?
  remove left padding for now? or add right padding?
* OQ: item menu style (bars / no bars, multiple items)
* OQ: description multi paragraph style?
-
* OQ: alternative item style (no header bottom bar, heading bold)
* OQ: edit mode and list of items (show with disabled buttons or hide)?
  on new it would be better hidden, so yeah, maybe hidden?

later important for move and trash:

* OQ: list meta data -- container as
  * Object attached to Object
  * class attached to Object
    * with prefixed fields (comments, comments_count, ...)
    * with subobject ({count, items, ...})
  * none - implement manually, trashable makes callback
* OQ: list functionality -- where to put move() / move_item()?
  * and with it - create() / create_item()?

---

class List(Object, Editable):
    """
    .. attribute:: items

       blabla.

       Has a create(title, text). *title* is foo and *text* is bar.
    """

    def __init__(self, id):
        #self.items = ListItemContainer('{}.items'.format(self.id), self._create_item)
        self.items = Container('{}.items'.format(self.id), self._create_item)

    def _create_item(self, title, text):
        pass

#class ListItemsContainer(Container):
#    def create(self, title, text):
#        pass

class Container(RedisSequence):
    def __init__(self, key, create):
        self._key = key
        self.create = create

    def move(self, item, to):
        # Copied from Meetling
        if to:
            if to.id not in self.items:
                raise ValueError('to_not_found')
            if to == item:
                # No op
                return
        if not self.app.r.lrem(self._items_key, 1, item.id):
            raise ValueError('item_not_found')
        if to:
            self.app.r.linsert(self._items_key, 'after', to.id, item.id)
        else:
            self.app.r.lpush(self._items_key, item.id)

    def _update_meta(self):
        # Updates count (and maybe list of authors)
        pass

class Trashable:
    def __init__(self, trashed, container):
        self.trashed = trashed
        self.__container = container

    def trash(self):
        self.trashed = True
        self.app.r.oset(self.id, self)
        self.__container._update_meta()

    def restore(self):
        self.trashed = False
        self.app.r.oset(self.id, self)
        self.__container._update_meta()

def make_list_endpoints(url, get_list, movable=False):
    return [(url + r'/move', _ListMoveEndpoint, {'get_list': get_list})]

class _ListMoveEndpoint(Endpoint):
    def post(self, *args):
        seq = self.get_list(*args)
        args = self.check_args({'item_id': str, 'to_id': (str, None)})
        seq.move(**args)
        self.write(json.dumps(None))

{
    "__type__": "User",
    "notifications": {
        "count": 7,
        "authors": ["a", "b", "c"],
        "items": [{"__type__": "Notification", ....}, ....] # OPT <- maybe even never, either summary or list of items?
    },
    "comments": ...
}

funny: list in api is just reference (multiple)
count, authors etc. is meta data to quickly *summarize* the items (if we got all items => no need to
summerize) => so list api endpoints should just return list, without meta data (right?)
but we could do it, because lists are always references of an object like /api/foo/id/items
so meta data available via foo/id

class List:
    def __init__(self, title, items):
        self.items = RefList(items, self)

    def json(self):
        return {'items': self.items.meta_json()}

class RefList(JSONRedisSequence):
    def __init__(self, data, master):
        super(self).__init__(key)
        self.count = data['count']
        self._author_ids = data['authors']
        self.master = master

    def meta_json(self):
        return {'count': self.count, 'authors': self._author_ids}

class Trashable:
    def trash(self):
        self.trashed = True
        self.__container.count -= 1
        self.app.r.omset({self.id: self, self.__container.master.id: self.__container.master})
        # could also call self.__container._trash(self) which can then modify count and update
        # authors
