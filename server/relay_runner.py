import asyncio

from .relay import run_relay


def main():
    asyncio.run(run_relay())


if __name__ == "__main__":
    main()
