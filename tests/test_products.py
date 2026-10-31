from emporio.tools.products import get_product, search_products


def test_takamine_gd20_price(conn):
    result = get_product(name="Takamine GD20", conn=conn)
    assert result["status"] == "found"
    assert result["product"]["product_id"] == 95
    assert result["product"]["price_brl"] == 2199.0
    assert result["product"]["price_text"] == "R$ 2.199,00"
    assert result["product"]["promotion"] is None


def test_name_lookup_tolerates_spacing_case_and_accents(conn):
    for text in ("takamine gd 20", "TAKAMINE gd20", "gd20"):
        assert get_product(name=text, conn=conn)["product"]["product_id"] == 95


def test_ambiguous_name_returns_candidates(conn):
    result = get_product(name="Yamaha", conn=conn)
    assert result["status"] == "ambiguous"
    assert len(result["candidates"]) > 1


def test_unknown_name_is_not_found(conn):
    assert get_product(name="Stradivarius", conn=conn)["status"] == "not_found"


def test_guitars_up_to_1000_only_available(conn):
    result = search_products(category="violões", max_price=1000, conn=conn)
    ids = {r["product_id"] for r in result["results"]}
    assert result["count"] == len(ids) > 5
    assert all(r["availability"] == "available" for r in result["results"])
    assert all(r["current_price_brl"] <= 1000 for r in result["results"])
    assert 96 not in ids      # out of stock (799.90)
    assert 113 not in ids     # discontinued (749.00)
    assert 83 in ids          # Tagima Memphis 429.90
    prices = [r["current_price_brl"] for r in result["results"]]
    assert prices == sorted(prices)


def test_out_of_stock_product_96(conn):
    product = get_product(product_id=96, conn=conn)["product"]
    assert product["availability"] == "out_of_stock"
    assert product["availability_label"] == "esgotado"
    assert product["stock_quantity"] is None
    hidden = search_products(query="GF-3D", conn=conn)
    shown = search_products(query="GF-3D", include_unavailable=True, conn=conn)
    assert hidden["count"] == 0
    assert [r["product_id"] for r in shown["results"]] == [96]


def test_discontinued_product_113(conn):
    product = get_product(product_id=113, conn=conn)["product"]
    assert product["availability"] == "discontinued"
    assert product["availability_label"] == "descontinuado"


def test_coming_soon_product_130(conn):
    product = get_product(product_id=130, conn=conn)["product"]
    assert product["availability"] == "coming_soon"
    assert product["availability_label"] == "em breve"
    assert product["stock_quantity"] is None   # stock is not sellable


def test_expired_promotion_is_ignored(conn):
    # 96 has two promotion rows (18% and 40%) but both are inactive
    assert get_product(product_id=96, conn=conn)["product"]["promotion"] is None
    assert get_product(product_id=93, conn=conn)["product"]["promotion"] is None


def test_active_promotion_90_is_18_percent(conn):
    promo = get_product(product_id=90, conn=conn)["product"]["promotion"]
    assert promo["discount_percent"] == 18
    assert promo["original_price_brl"] == 2399.0
    assert promo["promo_price_brl"] == 1967.18
    assert get_product(product_id=90, conn=conn)["product"]["current_price_brl"] == 1967.18


def test_exactly_four_active_promotions(conn):
    ids = {p["product_id"] for p in search_products(include_unavailable=True, limit=100, conn=conn)["results"]
           if p["promotion"]}
    assert ids == {90, 94, 121, 127}


def test_price_filter_uses_promotional_price(conn):
    # 121 lists at 549.00 but costs 439.20 with its active 20% promotion
    ids = {r["product_id"] for r in search_products(query="ohana ck-20", max_price=500, conn=conn)["results"]}
    assert ids == {121}


def test_unreliable_description_is_withheld(conn):
    product = get_product(product_id=142, conn=conn)["product"]
    assert product["description_reliable"] is False
    assert "description" not in product
    assert "description_note" in product
    assert product["specs"]["keys"] == "61"


def test_reliable_description_is_returned(conn):
    assert "description" in get_product(product_id=95, conn=conn)["product"]


def test_filters_string_type_and_electronics(conn):
    steel = search_products(category="violões", string_type="steel", has_electronics=True, conn=conn)
    assert steel["count"] > 0
    for r in steel["results"]:
        specs = get_product(product_id=r["product_id"], conn=conn)["product"]["specs"]
        assert specs["strings"] == "steel" and specs["electronics"] == "yes"


def test_empty_category_has_explanatory_note(conn):
    result = search_products(category="sopro", conn=conn)
    assert result["count"] == 0
    assert result["notes"]


def test_unknown_category(conn):
    assert search_products(category="acordeões", conn=conn)["count"] == 0


def test_plural_and_accent_insensitive_query(conn):
    assert search_products(query="ukuleles", conn=conn)["count"] > 0
    assert (search_products(query="violao", conn=conn)["count"]
            == search_products(query="VIOLÕES", conn=conn)["count"])
