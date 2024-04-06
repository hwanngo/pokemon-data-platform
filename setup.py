from setuptools import setup, find_packages

setup(
    name="pokemon-data-platform",
    version="1.0.0",
    description="A data platform for collecting and analyzing Pokémon data",
    author="Pokémon Data Platform Team",
    python_requires=">=3.10",
    packages=find_packages(),
    package_dir={"": "src"},
    install_requires=[
        "requests>=2.31.0",
        "pandas>=2.2.0",
        "numpy>=1.26.3",
        "sqlalchemy>=1.4.36,<2.0.0",
        "psycopg2-binary>=2.9.9",
        "backoff>=2.2.1",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "black>=23.0.0",
            "isort>=5.0.0",
            "flake8>=6.0.0",
        ]
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
    ],
)