# micro

Toolkit for social micro web apps.

For a quick introduction on how to build an application with micro, have a look at the included
example in `hello`.

## Requirements

The following software is required and must be set up on your system:

* Python >= 3.7
* Node.js >= 10.15
* Redis >= 5.0

micro should work on any [POSIX](https://en.wikipedia.org/wiki/POSIX) system.

## Installing dependencies

To install the dependencies for micro, type:

```sh
make deps
```

## Browser support

micro supports the latest version of popular browsers (i.e. Chrome, Edge, Firefox and Safari; see
http://caniuse.com/ ).

## Deprecation policy

Features marked as deprecated are removed after a period of six months.

## Boilerplate

The `boilerplate` directory contains base files for any micro app repository. They are not required,
but may come in handy when bootstrapping a new project.

Simply copy the files from `boilerplate` over to the new repository and substitute all place holders
(with curly braces, like `{name}`). Over time, extend the files as needed with app-specific details.

## Public domain components

While micro is covered by the [LGPL](https://www.gnu.org/licenses/lgpl.html), the following modules
are released into the public domain:

* [jsonredis](https://github.com/noyainrain/micro/blob/master/micro/jsonredis.py)
* [webapi](https://github.com/noyainrain/micro/blob/master/micro/webapi.py)
* [bind.js](https://github.com/noyainrain/micro/blob/master/client/bind.js)
* [keyboard.js](https://github.com/noyainrain/micro/blob/master/client/keyboard.js)

## Contributors

* Sven James &lt;sven AT inrain.org>

Copyright (C) 2018 micro contributors
