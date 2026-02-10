from setuptools import setup, find_packages
from pathlib import Path

long_description = ""
readme = Path(__file__).parent / "README.md"
if readme.exists():
    long_description = readme.read_text(encoding="utf-8")

setup(
    name="agent-memory",
    version="0.2.0",
    description="Lightweight memory management toolkit for AI agents",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Gendolf",
    url="https://github.com/Danieliushka/agent-memory",
    license="MIT",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[],
    extras_require={
        "semantic": ["openai>=1.0"],
    },
    entry_points={
        "console_scripts": [
            "agent-memory=agent_memory.cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Libraries",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
)
