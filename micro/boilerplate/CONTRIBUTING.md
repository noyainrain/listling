# Contributing to {name}

## How to contribute

1. For any non-trivial contribution:
   1. [Create an issue]({url}/issues) describing the intended change [1]
   2. A team member reviews your draft. Make the requested changes, if any.
2. Create a topic branch
3. Code...
4. [Create a pull request]({url}/pulls)
5. Travis CI runs the code quality checks. Fix the reported issues, if any.
6. A team member reviews your contribution. Make the requested changes, if any.
7. A team member merges your contribution \o/

[1] A good description contains:

* If the API or web API is modified, any method signature (including the return value and possible
  errors) and object signature (including properties)
* If the UI is modified, a simple sketch
* If a new dependency is introduced, a short description of the dependency and possible alternatives
  and the reason why it is the best option

## Requirements

A supported browser (e.g. Firefox) along with a WebDriver implementation (e.g. geckodriver) are
required for the UI tests and must be set up on your system.

## Installing development dependencies

To install the development dependencies for {name}, type:

```sh
make deps-dev
```

## Running the unit tests

To run all unit tests, type:

```sh
make
```

## Development utilities

The Makefile that comes with {name} provides additional utilities for different development tasks.
To get an overview, type:

```sh
make help
```

## Architecture overview

```
╭─────────╮
│ Server  │
├─────────┤
│ micro   │
│   ↓     │
│ Tornado │
│   ↓     │   ╭───────╮
│ Python  │ ⇒ │ Redis │
╰─────────╯   ╰───────╯
  ⇑
╭─────────────────────╮
│ Client              │
├─────────────────────┤
│ micro       bind.js │
│   ↓           ↓     │
│ JavaScript  HTML    │
╰─────────────────────╯
```
