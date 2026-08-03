"""
Setuptools build script for NexusAI editable installation compatibility.
"""

from setuptools import find_packages, setup

setup(
    name="nexusai",
    version="0.1.0",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    entry_points={
        "console_scripts": [
            "nexusai = nexusai.cli.app:app",
        ],
    },
)
