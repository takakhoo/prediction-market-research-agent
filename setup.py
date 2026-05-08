from setuptools import find_packages, setup

setup(
    name="polymarket-news-agent",
    version="0.1.0",
    description="Telegram discovery dashboard MVP for channel discovery",
    packages=find_packages(include=["src", "src.*"]),
    python_requires=">=3.9",
    install_requires=[
        "aiotdlib==0.27.6",
        "fastapi>=0.110,<1.0",
        "uvicorn[standard]>=0.29,<1.0",
        "jinja2>=3.1,<4.0",
        "aiosqlite>=0.20,<1.0",
        "psycopg[binary]>=3.1,<4.0",
        "pydantic-settings>=2.1,<3.0",
    ],
    extras_require={
        "dev": [
            "pytest>=8,<9",
            "pytest-asyncio>=0.23,<1.0",
            "httpx>=0.27,<1.0",
        ]
    },
)
