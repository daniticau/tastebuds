"""Check the live Jev connection with one real request.

Needs TASTEBUDS_TYPESAFE_API_KEY (and TASTEBUDS_DATABASE_URL, which the settings require).
Run: python -m scripts.check_jev
"""

import asyncio
import time

from tastebuds import decisions
from tastebuds.config import get_settings


async def check() -> None:
    if not get_settings().typesafe_api_key:
        print("TASTEBUDS_TYPESAFE_API_KEY is not set. Jev is off and the fixed rules apply.")
        return

    started = time.perf_counter()
    decision = await decisions.decide_place(
        name="Tajima Ramen",
        city="San Diego",
        neighborhood="Convoy",
        hints=["tonkotsu ramen"],
        candidates=[
            decisions.KnownPlace("Tajima", "Kearny Mesa", ["ramen"]),
            decisions.KnownPlace("Tajimi Sushi Bar", "Hillcrest", ["sushi"]),
        ],
        need_cuisine=True,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000
    await decisions.close_client()

    if decision is None:
        print("No usable answer. Check the key, the model name, and the log line above.")
        return
    print(f"Answered in {elapsed_ms:.0f} ms")
    print(f"  same place as known place: {decision.same_as} (expected 0)")
    print(f"  cuisine: {decision.cuisine} (expected ramen)")


if __name__ == "__main__":
    asyncio.run(check())
