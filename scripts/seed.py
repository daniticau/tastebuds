"""Seed the database with well-known San Diego restaurants.

Idempotent: a place that already exists is not added again.
Run: python -m scripts.seed
"""

import asyncio

from tastebuds.db.client import close_db_pool, get_pool, init_db_pool
from tastebuds.db.queries import find_or_create_place

SEED_PLACES = [
    # (name, city, neighborhood, cuisine_tags)
    ("Sab E Lee", "San Diego", "North Park", ["thai"]),
    ("Supannee House", "San Diego", "Kearny Mesa", ["thai"]),
    ("Tajima Ramen", "San Diego", "Hillcrest", ["japanese", "ramen"]),
    ("Underbelly", "San Diego", "Little Italy", ["japanese", "ramen"]),
    ("Tacos El Gordo", "San Diego", "Chula Vista", ["mexican", "tacos"]),
    ("Lolita's Mexican Food", "San Diego", "Kearny Mesa", ["mexican"]),
    ("Vallarta Express", "San Diego", "Barrio Logan", ["mexican", "tacos"]),
    ("Convoy Tofu House", "San Diego", "Kearny Mesa", ["korean"]),
    ("Friend's House", "San Diego", "Kearny Mesa", ["korean", "bbq"]),
    ("Dumpling Inn", "San Diego", "Kearny Mesa", ["chinese", "dumplings"]),
    ("Din Tai Fung", "San Diego", "UTC", ["chinese", "dumplings"]),
    ("Crack Shack", "San Diego", "Little Italy", ["american", "chicken"]),
    ("Hodad's", "San Diego", "Ocean Beach", ["american", "burgers"]),
    ("Rocky's Crown Pub", "San Diego", "Pacific Beach", ["american", "burgers"]),
    ("Phil's BBQ", "San Diego", "Point Loma", ["bbq"]),
    ("Bali Hai", "San Diego", "Point Loma", ["tiki", "seafood"]),
    ("Ironside Fish & Oyster", "San Diego", "Little Italy", ["seafood"]),
    ("Juniper & Ivy", "San Diego", "Little Italy", ["american", "fine dining"]),
    ("Addison", "San Diego", "Del Mar", ["french", "fine dining"]),
    ("Cucina Urbana", "San Diego", "Bankers Hill", ["italian"]),
    ("Bencotto", "San Diego", "Little Italy", ["italian", "pasta"]),
    ("Extraordinary Desserts", "San Diego", "Bankers Hill", ["dessert", "cafe"]),
    ("Better Buzz Coffee", "San Diego", "Pacific Beach", ["coffee"]),
    ("Bird Rock Coffee Roasters", "San Diego", "La Jolla", ["coffee"]),
    ("Cross Street Chicken and Beer", "San Diego", "Kearny Mesa", ["korean", "chicken"]),
    ("Pho Hoa", "San Diego", "City Heights", ["vietnamese", "pho"]),
    ("Shabu Shabu House", "San Diego", "Kearny Mesa", ["japanese", "hot pot"]),
    ("The Taco Stand", "San Diego", "La Jolla", ["mexican", "tacos"]),
    ("Werewolf", "San Diego", "Gaslamp", ["american", "brunch"]),
    ("Morning Glory", "San Diego", "Little Italy", ["american", "brunch"]),
    ("Herb & Wood", "San Diego", "Little Italy", ["american", "mediterranean"]),
    ("Civico 1845", "San Diego", "Little Italy", ["italian"]),
    ("Puesto", "San Diego", "La Jolla", ["mexican", "tacos"]),
    ("Akinori Sushi", "San Diego", "Kearny Mesa", ["japanese", "sushi"]),
    ("Sushi Ota", "San Diego", "Pacific Beach", ["japanese", "sushi"]),
    ("Oscar's Mexican Seafood", "San Diego", "Hillcrest", ["mexican", "seafood"]),
    ("Lucha Libre Taco Shop", "San Diego", "Mission Hills", ["mexican", "tacos"]),
    ("Mike's Taco Club", "San Diego", "Ocean Beach", ["mexican", "tacos"]),
    ("OB Noodle House", "San Diego", "Ocean Beach", ["asian", "noodles"]),
    ("Mama's Bakery", "San Diego", "Normal Heights", ["lebanese", "bakery"]),
]


async def seed() -> None:
    """Insert seed places, skipping duplicates."""
    await init_db_pool()
    pool = await get_pool()
    before = await pool.fetchval("SELECT COUNT(*) FROM places")

    for name, city, neighborhood, tags in SEED_PLACES:
        # The same path as live feedback: dedup, cuisine parents, tags from the name.
        await find_or_create_place(
            name=name,
            city=city,
            neighborhood=neighborhood,
            cuisine_tags=tags,
        )

    inserted = await pool.fetchval("SELECT COUNT(*) FROM places") - before
    await close_db_pool()
    print(f"Seed complete: {inserted} inserted, {len(SEED_PLACES) - inserted} already there")


if __name__ == "__main__":
    asyncio.run(seed())
