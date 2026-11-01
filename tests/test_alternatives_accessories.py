import pytest

from emporio.tools.products import get_product, search_products


def _string_types(conn, alts):
    return {conn.execute("SELECT string_type FROM products WHERE product_id = ?",
                         (a["product_id"],)).fetchone()[0] for a in alts}


def _price(item):
    return item["current_price_brl"]


# ---- alternatives for unavailable products ----------------------------------------------

def test_out_of_stock_96_gets_three_available_steel_alternatives(conn):
    product = get_product(product_id=96, conn=conn)["product"]
    alts = product["alternatives"]
    assert len(alts) == 3
    assert all(a["availability"] == "available" for a in alts)
    assert all(a["category"] == product["category"] for a in alts)
    assert _string_types(conn, alts) == {"steel"}
    assert not any("7 Cordas" in a["name"] for a in alts)  # a 6-string guitar gets 6-string options
    distances = [abs(_price(a) - 799.90) for a in alts]
    assert distances == sorted(distances)  # closest price first


def test_discontinued_113_gets_only_seven_string_nylon_alternatives(conn):
    alts = get_product(product_id=113, conn=conn)["product"]["alternatives"]
    # "7 cordas" is only in the name (not a structured spec); names are the source of truth.
    assert [a["product_id"] for a in alts] == [110, 109, 111]
    assert all("7 Cordas" in a["name"] for a in alts)
    assert _string_types(conn, alts) == {"nylon"}  # the spec, not the name, says nylon


def test_search_attaches_alternatives_only_to_unavailable_items(conn):
    out = search_products(query="Giannini GF-3D", include_unavailable=True, conn=conn)
    assert out["count"] == 1 and len(out["results"][0]["alternatives"]) == 3
    available = search_products(query="Takamine GD20", conn=conn)["results"][0]
    assert "alternatives" not in available
    assert "alternatives" not in get_product(product_id=95, conn=conn)["product"]


@pytest.mark.parametrize("product_id", [130, 136])
def test_coming_soon_and_discontinued_alternatives_are_available_same_category(conn, product_id):
    product = get_product(product_id=product_id, conn=conn)["product"]
    assert product["availability"] != "available"
    alts = product["alternatives"]
    assert len(alts) <= 3
    assert all(a["availability"] == "available" and a["category"] == product["category"] for a in alts)
    if not alts:
        assert product["alternatives_note"]


# ---- accessories are not sold -------------------------------------------------------------

@pytest.mark.parametrize("query", [
    "cordas de violão", "corda de nylon", "encordoamento", "cabo para guitarra", "palhetas",
    "pedal de efeito", "amplificador", "caixa amplificada", "case para violão", "capa",
    "bag", "afinador", "afinador avulso", "estante de partitura", "baquetas", "correia",
    "Palheta Dunlop", "AMPLIFICADOR Marshall",
])
def test_accessory_queries_are_flagged(conn, query):
    out = search_products(query=query, conn=conn)
    assert out["not_sold_accessory"] is True
    assert out["count"] == 0 and out["results"] == []
    assert "exclusivamente" in out["message"]


@pytest.mark.parametrize("query", [
    "violão de 7 cordas", "violão 12 cordas", "baixo 5 cordas", "Tagima Dallas Tuner",
    "violão com afinador integrado", "violão", "violão com cordas de aço", "sete cordas",
    "Takamine",
])
def test_instrument_queries_are_not_accessories(conn, query):
    out = search_products(query=query, conn=conn)
    assert "not_sold_accessory" not in out


def test_dallas_tuner_is_still_found(conn):
    out = search_products(query="Dallas Tuner", conn=conn)
    assert out["count"] == 1 and "Tuner" in out["results"][0]["name"]


@pytest.mark.parametrize("query", [
    "pedais", "amplificadores", "afinadores", "cabos", "cases", "capas", "baquetas",
    "correias", "estantes", "vocês vendem pedais?", "pedais de efeito", "AMPLIFICADORES valvulados",
])
def test_accessory_plurals_are_flagged(conn, query):
    out = search_products(query=query, conn=conn)
    assert out.get("not_sold_accessory") is True, query


@pytest.mark.parametrize("query", [
    "violão com afinadores integrados", "violões de 7 cordas",
])
def test_plural_instrument_features_are_not_accessories(conn, query):
    assert "not_sold_accessory" not in search_products(query=query, conn=conn)
