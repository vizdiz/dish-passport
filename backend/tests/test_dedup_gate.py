"""The load-bearing test: the dedup gate must not break.

Paraphrases of the same dish link to one canonical row; kindred-but-distinct dishes
(al pastor ~ shawarma) stay apart because DEDUP_TAU sits above their similarity.
"""
from __future__ import annotations

import logging

import pytest

from app.adapters.repo_memory import InMemoryDishRepository, _cosine
from app.ports import NormalizedDish
from app.services.ingestion import DishNotFound, log_dish
from tests.fakes import StubEmbedder, StubNormalizer, axis0, flat_flavor, vec_cos_to_axis0

TAU = 0.90


async def _gate(repo, embedder, normalizer, **kw):
    return await log_dish(repo=repo, embedder=embedder, normalizer=normalizer, tau=TAU, **kw)


def _seed_axis0(repo, name="Anchor", description="anchor dish") -> int:
    return repo.seed_dish(
        name=name, description=description, flavor=flat_flavor(),
        embedding=axis0(),
    ).id


# --------------------------------------------------------------------------- fast lane

async def test_fastlane_links_without_llm_or_embed(repo):
    dish_id = _seed_axis0(repo, name="Pad Thai")
    embedder, normalizer = StubEmbedder(), StubNormalizer()

    result = await _gate(repo, embedder, normalizer, user_id=1, dish_id=dish_id)

    assert result.is_new is False
    assert result.dish.id == dish_id
    assert embedder.calls == 0 and normalizer.calls == 0   # zero LLM, zero embed
    assert repo.dish_count == 1


async def test_fastlane_unknown_dish_id_raises(repo):
    with pytest.raises(DishNotFound):
        await _gate(repo, StubEmbedder(), StubNormalizer(), user_id=1, dish_id=999)


# --------------------------------------------------------------------------- mint / link

async def test_empty_catalog_mints_first_dish(repo):
    result = await _gate(repo, StubEmbedder(), StubNormalizer(), user_id=1, text="som tum")
    assert result.is_new is True
    assert repo.dish_count == 1


async def test_paraphrase_links_existing(repo):
    desc = "grilled spiced yogurt-marinated chicken pieces"
    repo.seed_dish(name="Chicken Tikka", description=desc, flavor=flat_flavor(),
                   embedding=axis0())
    normalizer = StubNormalizer(mapping={"murgh tikka": desc})
    embedder = StubEmbedder(mapping={desc: vec_cos_to_axis0(0.97)})

    result = await _gate(repo, embedder, normalizer, user_id=1, text="murgh tikka")

    assert result.is_new is False                  # 0.97 >= 0.90 -> link
    assert result.dish.name == "Chicken Tikka"
    assert repo.dish_count == 1


async def test_distinct_dish_mints_new(repo):
    _seed_axis0(repo)
    normalizer = StubNormalizer(mapping={"miso soup": "fermented soybean broth with tofu"})
    embedder = StubEmbedder(mapping={"fermented soybean broth with tofu": vec_cos_to_axis0(0.20)})

    result = await _gate(repo, embedder, normalizer, user_id=1, text="miso soup")

    assert result.is_new is True                   # 0.20 < 0.90 -> mint
    assert repo.dish_count == 2


async def test_kindred_cross_cuisine_not_collapsed(repo):
    """The constraint the whole gate exists to honor: TAU > kindred similarity (~0.85)."""
    repo.seed_dish(
        name="Al Pastor",
        description="spit-roasted marinated pork shaved thin, served with pineapple",
        flavor=flat_flavor(), embedding=axis0(),
    )
    shawarma_desc = "spit-roasted marinated meat shaved thin from a vertical rotisserie"
    normalizer = StubNormalizer(mapping={"shawarma": shawarma_desc})
    embedder = StubEmbedder(mapping={shawarma_desc: vec_cos_to_axis0(0.85)})

    result = await _gate(repo, embedder, normalizer, user_id=1, text="shawarma")

    assert result.is_new is True                   # 0.85 < 0.90 -> distinct, NOT collapsed
    assert repo.dish_count == 2


async def test_tau_boundary_is_inclusive(repo):
    """cosine == TAU links (>=); a hair below mints. Uses the repo's own cosine to avoid
    floating-point ambiguity at the threshold."""
    desc = "boundary dish"
    vec = vec_cos_to_axis0(0.90)
    exact = _cosine(axis0(), vec)                   # the value the gate will actually compare

    # link side: TAU exactly equal to the neighbor cosine.
    link_repo = InMemoryDishRepository()
    link_repo.seed_dish(name="Anchor", description="anchor", flavor=flat_flavor(), embedding=axis0())
    n = StubNormalizer(mapping={"x": desc})
    e = StubEmbedder(mapping={desc: vec})
    res_link = await log_dish(repo=link_repo, embedder=e, normalizer=n, user_id=1,
                              text="x", tau=exact)
    assert res_link.is_new is False
    assert link_repo.dish_count == 1

    # mint side: TAU a hair above the neighbor cosine.
    mint_repo = InMemoryDishRepository()
    mint_repo.seed_dish(name="Anchor", description="anchor", flavor=flat_flavor(), embedding=axis0())
    res_mint = await log_dish(repo=mint_repo, embedder=StubEmbedder(mapping={desc: vec}),
                              normalizer=StubNormalizer(mapping={"x": desc}), user_id=1,
                              text="x", tau=exact + 1e-6)
    assert res_mint.is_new is True
    assert mint_repo.dish_count == 2


async def test_link_reuses_existing_canonical_flavor(repo):
    """On link, the canonical dish's flavor wins; the new entry's scored flavor is discarded."""
    canonical_flavor = [0.9, 0.1, 0.0, 0.2, 0.0, 0.8, 0.0, 0.0, 0.0, 0.1]
    desc = "rich braised beef"
    repo.seed_dish(name="Beef Stew", description=desc, flavor=canonical_flavor, embedding=axis0())
    # The normalizer would score a *different* flavor for the paraphrase...
    normalizer = StubNormalizer(
        mapping={"boeuf bourguignon": NormalizedDish(
            name="Boeuf", description=desc, flavor=[0.1] * 10)}
    )
    embedder = StubEmbedder(mapping={desc: vec_cos_to_axis0(0.99)})

    result = await _gate(repo, embedder, normalizer, user_id=1, text="boeuf bourguignon")

    assert result.is_new is False
    assert result.dish.flavor == canonical_flavor   # reused, not the [0.1]*10 from the new score


# --------------------------------------------------------------------------- side effects

async def test_log_bumps_user_log_count(repo):
    dish_id = _seed_axis0(repo)
    await _gate(repo, StubEmbedder(), StubNormalizer(), user_id=7, dish_id=dish_id)
    await _gate(repo, StubEmbedder(), StubNormalizer(), user_id=7, dish_id=dish_id)
    assert repo.log_count(7) == 2


async def test_sentiment_is_recorded(repo):
    dish_id = _seed_axis0(repo)
    await _gate(repo, StubEmbedder(), StubNormalizer(), user_id=1, dish_id=dish_id,
                sentiment="disliked", rating=2, notes="too salty")
    assert repo.logs[-1]["sentiment"] == "disliked"
    assert repo.logs[-1]["rating"] == 2


async def test_every_decision_is_logged(repo, caplog):
    caplog.set_level(logging.INFO, logger="dishport.ingestion")

    # mint
    await _gate(repo, StubEmbedder(), StubNormalizer(), user_id=1, text="novel dish")
    # link
    desc = "anchor desc"
    anchor = repo.seed_dish(name="Anchor", description=desc, flavor=flat_flavor(), embedding=axis0())
    await _gate(repo, StubEmbedder(mapping={desc: vec_cos_to_axis0(0.99)}),
                StubNormalizer(mapping={"again": desc}), user_id=1, text="again")
    # fastlane
    await _gate(repo, StubEmbedder(), StubNormalizer(), user_id=1, dish_id=anchor.id)

    text = caplog.text
    assert "dedup decision=mint" in text
    assert "dedup decision=link" in text
    assert "dedup decision=fastlane" in text
    assert "tau=0.90" in text                        # cosine + tau present for review
