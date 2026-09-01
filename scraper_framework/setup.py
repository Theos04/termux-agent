# setup.py
"""Setup script for the scraper framework"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="scraper-framework",
    version="1.0.0",
    author="Your Name",
    description="Multi-partition web scraping framework with Chrome automation",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/scraper-framework",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.7",
    install_requires=[
        "celery>=5.0.0",
        "aiohttp>=3.8.0",
        "google-sheets-db>=1.0.0",
        "croniter>=1.0.0",
        "pathlib>=1.0.0",
    ],
    entry_points={
        "console_scripts": [
            "scraper-cli=cli.main:main",
            "scraper-api=api.server:run_api_server",
        ],
    },
)
