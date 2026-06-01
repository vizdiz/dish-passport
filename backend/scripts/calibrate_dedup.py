"""Empirically calibrate DEDUP_TAU on real embeddings, using the ENRICHED embedding text
(name + description + ingredients + prep). Groups encode ground truth: phrasings within a
group are the same dish (should LINK); across groups are distinct (should NOT link). Prints
the should-link vs should-not-link cosine distributions and a recommended tau.

    DP_OPENAI_API_KEY=... PYTHONPATH=. python scripts/calibrate_dedup.py
"""
from __future__ import annotations

import asyncio
import itertools

import numpy as np

from app.adapters.embeddings_openai import OpenAIEmbedder
from app.adapters.llm_openai import OpenAINormalizer
from app.config import Settings
from app.services.ingestion import embedding_text

# label -> phrasings. Multi-phrasing groups are true duplicates (should link).
GROUPS: dict[str, list[str]] = {
    "tikka_masala": ["chicken tikka masala", "murgh tikka masala"],
    "shrimp_fried_rice": ["shrimp fried rice", "prawn fried rice"],
    "eggplant_parm": ["eggplant parmesan", "aubergine parmigiana"],
    "grilled_cheese": ["grilled cheese sandwich", "toasted cheese sandwich"],
    "fries": ["french fries", "pommes frites"],
    "chana": ["chickpea curry", "chana masala"],
    # distinct singletons (some intentionally similar-but-different)
    "ceviche": ["ceviche"], "larb": ["larb"],
    "al_pastor": ["tacos al pastor"], "shawarma": ["chicken shawarma"],
    "ramen": ["ramen"], "pho": ["pho"],
    "carbonara": ["spaghetti carbonara"], "miso": ["miso soup"],
    "tom_yum": ["tom yum goong"], "caesar": ["caesar salad"],
    "guacamole": ["guacamole"], "hummus": ["hummus"],
    "pad_thai": ["pad thai"], "margherita": ["margherita pizza"],
    "tiramisu": ["tiramisu"], "falafel": ["falafel"],
    "kimchi": ["kimchi"], "butter_chicken": ["butter chicken"],
}


def cosine(a, b) -> float:
    a, b = np.asarray(a), np.asarray(b)
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))


async def main() -> None:
    s = Settings()
    if not s.openai_api_key:
        raise SystemExit("DP_OPENAI_API_KEY required")
    embedder = OpenAIEmbedder(s.openai_api_key, s.embedding_model)
    normalizer = OpenAINormalizer(s.openai_api_key, s.flavor_model)

    items: list[tuple[str, str, list[float]]] = []  # (group, phrasing, vector)
    print("embedding (enriched text)...")
    for group, phrasings in GROUPS.items():
        for phrasing in phrasings:
            nd = await normalizer.normalize(phrasing)
            vec = await embedder.embed(embedding_text(nd))
            items.append((group, phrasing, vec))
    print(f"  {len(items)} dishes embedded\n")

    dup, distinct = [], []
    for (g1, p1, v1), (g2, p2, v2) in itertools.combinations(items, 2):
        c = cosine(v1, v2)
        (dup if g1 == g2 else distinct).append((c, f"{p1} ~ {p2}"))

    print("== SHOULD-LINK (same dish, different phrasing) ==")
    for c, lbl in sorted(dup, reverse=True):
        print(f"  {c:.4f}  {lbl}")
    print("\n== top SHOULD-NOT-LINK (distinct dishes) ==")
    for c, lbl in sorted(distinct, reverse=True)[:12]:
        print(f"  {c:.4f}  {lbl}")

    min_dup = min(c for c, _ in dup)
    max_dist = max(c for c, _ in distinct)
    print(f"\n  min(should-link)     = {min_dup:.4f}")
    print(f"  max(should-not-link) = {max_dist:.4f}")
    if min_dup > max_dist:
        tau = round((min_dup + max_dist) / 2, 2)
        print(f"  ✅ clean gap -> recommend DEDUP_TAU = {tau}")
    else:
        cands = sorted({c for c, _ in dup} | {c for c, _ in distinct})
        best_t, best_correct = 0.0, -1
        total = len(dup) + len(distinct)
        for t in cands:
            correct = sum(c >= t for c, _ in dup) + sum(c < t for c, _ in distinct)
            if correct > best_correct:
                best_t, best_correct = t, correct
        print(f"  ⚠ overlap (some distinct pairs >= some dup pairs).")
        print(f"  best-accuracy DEDUP_TAU ~ {round(best_t, 2)} "
              f"({best_correct}/{total} pairs classified correctly)")


if __name__ == "__main__":
    asyncio.run(main())
