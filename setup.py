"""
setup.py - a module to allow package installation
"""

from setuptools import setup, find_packages

NAME = "slab"
VERSION = "0.1"
DEPENDENCIES = [
    "numpy",
    "pyro4",
    "scipy",
    "tabulate",
    "pyvisa"
]
DESCRIPTION = "This package is used for Schuster Lab experiments"
AUTHOR = "David Schuster"
AUTHOR_EMAIL = "david.schuster@uchicago.edu"

setup(author=AUTHOR,
      author_email=AUTHOR_EMAIL,
      description=DESCRIPTION,
      install_requires=DEPENDENCIES,
      name=NAME,
      version=VERSION,
      packages=find_packages(),
)