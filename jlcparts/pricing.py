def get_quantity_price(quantity, pricelist):
    """Return the unit price tier selected by the frontend quantity logic."""
    if not pricelist:
        return None

    for pricepoint in pricelist:
        if not isinstance(pricepoint, dict):
            continue
        q_from = pricepoint.get("qFrom")
        if q_from is None:
            continue
        q_to = pricepoint.get("qTo")
        if quantity >= q_from and (not q_to or quantity <= q_to):
            price = pricepoint.get("price")
            return None if price is None else float(price)

    fallback = pricelist[0].get("price") if isinstance(pricelist[0], dict) else None
    return None if fallback is None else float(fallback)
