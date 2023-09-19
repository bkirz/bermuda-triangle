# Bermuda Δ Triangle
This is the source code for https://bermudatriangle.tech, a collection of tools for use with
StepMania simfiles.

## Development
The core webapp is built using Flask and uses [Poetry](https://python-poetry.org) for dependency management.
The project is known to work with Python 3.11.5 and Poetry 1.6.1.
Using older versions of Poetry and Python may lead to command failures with unintuitive error messages.

To run it locally:
```
# install dependencies (you may need to install poetry first)
$ poetry install

# start flask
$ poetry run flask run
```
