import setuptools

from uitk import __package__, __version__
import pythontk as ptk


long_description = ptk.get_file_contents("docs/README.md")
description = ptk.get_text_between_delimiters(
    long_description,
    "<!-- short_description_start -->",
    "<!-- short_description_end -->",
    as_string=True,
)

# Read requirements.txt and add to install_requires
with open("requirements.txt") as f:
    required_packages = f.read().splitlines()

setuptools.setup(
    name=__package__,
    version=__version__,
    author="Ryan Simpson",
    author_email="m3trik@outlook.com",
    license="LGPLv3",
    description=description,
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/m3trik/uitk",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU Library or Lesser General Public License (LGPL)",
        "Operating System :: OS Independent",
    ],
    packages=setuptools.find_packages(),  # scan the directory structure and include all package dependancies.
    include_package_data=True,
    install_requires=required_packages,
    data_files=ptk.get_dir_contents(
        __package__, "filepath", exc_files=["*.py", "*.pyc", "*.json"]
    ),  # ie. ('uitk/ui/0', ['uitk/ui/0/init.ui']),
)

# --------------------------------------------------------------------------------------------


# --------------------------------------------------------------------------------------------
# Notes
# --------------------------------------------------------------------------------------------
