from setuptools import setup, find_packages

setup(
    name="agent-memory",
    version="0.1.0",
    description="Lightweight memory management toolkit for AI agents",
    author="Gendolf",
    url="https://github.com/Danieliushka/agent-memory",
    packages=find_packages(),
    python_requires=">=3.8",
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
    ],
)
