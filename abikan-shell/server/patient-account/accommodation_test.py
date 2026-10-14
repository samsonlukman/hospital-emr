from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import accommodation as lodging
from server import ApiError


class AccommodationCurrencyTests(unittest.TestCase):
    def test_new_charges_use_ngn_pricelist_not_company_usd(self) -> None:
        odoo = MagicMock()
        odoo.search_read.side_effect = [
            [{"id": 10}],
            [{"id": 41, "complete_name": "All / Services / Accommodation"}],
            *[
                [
                    {
                        "id": 2393 + i,
                        "name": area["name"],
                        "list_price": 0,
                        "taxes_id": [],
                        "default_code": area["uuid"],
                        "categ_id": [41, "Accommodation"],
                    }
                ]
                for i, area in enumerate(lodging.AREAS)
            ],
            [{"id": 7, "name": "Hospital Accommodation", "currency_id": [2, "USD"]}],
            [
                {
                    "id": 6,
                    "name": "Accommodation",
                    "warehouse_id": [1, "WH"],
                    "pricelist_id": [1, "Public"],
                    "payment_default_id": [1, "Immediate"],
                }
            ],
        ]
        writes: list[tuple] = []

        def execute(_odoo, model, method, args, kwargs=None):
            writes.append((model, method, args))
            if model == "res.currency" and method == "search_read":
                return [{"id": 121, "active": True}]
            if method == "write":
                return True
            if method == "create":
                return 99
            return []

        with patch.object(lodging, "execute", side_effect=execute):
            masters = lodging.ensure_accommodation_masters(odoo)
        pricelist_writes = [row for row in writes if row[0] == "product.pricelist"]
        shop_writes = [row for row in writes if row[0] == "sale.shop"]
        self.assertTrue(pricelist_writes)
        self.assertEqual(pricelist_writes[0][2][1]["currency_id"], 121)
        self.assertTrue(shop_writes)
        self.assertEqual(shop_writes[0][2][1]["pricelist_id"], 7)
        self.assertEqual(masters["pricelist_id"], 7)

    def test_tariff_display_uses_naira_not_company_dollars(self) -> None:
        odoo = MagicMock()
        with (
            patch.object(lodging, "require_tariff_reader", return_value={"uuid": "admin"}),
            patch.object(lodging, "odoo_reader", return_value=odoo),
            patch.object(
                lodging,
                "ensure_accommodation_masters",
                return_value={"products": [{"default_code": lodging.AREAS[0]["uuid"], "list_price": 55000}]},
            ),
            patch.object(
                lodging,
                "accommodation_currency",
                return_value={"code": "NGN", "symbol": "₦", "decimalPlaces": 2, "position": "before"},
            ),
            patch.object(lodging, "format_money", return_value="₦55,000.00"),
        ):
            payload = lodging.list_tariffs("JSESSIONID=admin")
        hawawu = next(row for row in payload["areas"] if row["areaName"] == "Hawawu Maternity Ward")
        self.assertEqual(payload["currency"]["code"], "NGN")
        self.assertEqual(payload["currency"]["symbol"], "₦")
        self.assertEqual(hawawu["listPrice"], "₦55,000.00")

    def test_missing_tariff_still_refuses_a_zero_price(self) -> None:
        with self.assertRaises(ApiError) as raised:
            lodging.approved_tariff({"list_price": 0})
        self.assertEqual(raised.exception.code, "tariff_missing")
        self.assertEqual(
            lodging.TARIFF_MISSING,
            "Accommodation price is not configured for this bed/ward. "
            "Please contact Hospital Admin to configure the accommodation tariff.",
        )
        self.assertEqual(raised.exception.message, lodging.TARIFF_MISSING)
        self.assertNotIn("Daily room price is not set yet", lodging.TARIFF_MISSING)


class AccommodationPriceLifecycleTests(unittest.TestCase):
    def test_new_charge_uses_current_tariff_and_later_change_does_not_rewrite_it(self) -> None:
        stored: dict[str, tuple[dict, dict]] = {}
        product = {"id": 88, "list_price": 10000.0, "default_code": lodging.AREAS[0]["uuid"]}
        writes: list[tuple] = []

        def create_posted(odoo, **kwargs):
            key = kwargs["key"]
            price = kwargs["price"]
            if key in stored:
                return stored[key][0], stored[key][1], True
            line = {"price_unit": price, "external_order_id": key}
            sale = {"name": "SO-ACC", "amount_total": price, "currency_id": [121, "NGN"]}
            stored[key] = (line, sale)
            return line, sale, False

        start = lodging.datetime(2026, 9, 1, 9, 0, tzinfo=lodging.timezone.utc)
        with (
            patch.object(lodging, "find_accommodation_product", return_value=product),
            patch.object(lodging, "find_existing_sale", side_effect=lambda _odoo, key: stored.get(key)),
            patch.object(lodging, "create_posted_charge", side_effect=create_posted),
        ):
            first = lodging.ensure_day_one(
                MagicMock(),
                partner={"id": 4},
                area_uuid=lodging.AREAS[0]["uuid"],
                area_name=lodging.AREAS[0]["name"],
                bed_number="1",
                assignment_key="enc-1",
                start=start,
            )
            self.assertEqual(first["amount"], 10000.0)
            first_key = first["key"]
            product["list_price"] = 12000.0
            again = lodging.ensure_day_one(
                MagicMock(),
                partner={"id": 4},
                area_uuid=lodging.AREAS[0]["uuid"],
                area_name=lodging.AREAS[0]["name"],
                bed_number="1",
                assignment_key="enc-1",
                start=start,
            )
            self.assertIsNone(again)
            self.assertEqual(stored[first_key][0]["price_unit"], 10000.0)

            later = lodging.ensure_day_one(
                MagicMock(),
                partner={"id": 4},
                area_uuid=lodging.AREAS[0]["uuid"],
                area_name=lodging.AREAS[0]["name"],
                bed_number="2",
                assignment_key="enc-2",
                start=start,
            )
            self.assertEqual(later["amount"], 12000.0)
            self.assertEqual(stored[first_key][0]["price_unit"], 10000.0)
            self.assertEqual(len(stored), 2)

        product["list_price"] = 10000.0

        def execute(_odoo, model, method, args, kwargs=None):
            writes.append((model, method, args))
            return True

        with (
            patch.object(
                lodging,
                "require_admin_user",
                return_value={"uuid": "ha-1", "username": "hospitaladmin.abikan", "privileges": ["abikan:admin:staff"]},
            ),
            patch.object(lodging, "odoo_reader", return_value=MagicMock()),
            patch.object(lodging, "ensure_accommodation_masters", return_value={}),
            patch.object(lodging, "find_accommodation_product", return_value=product),
            patch.object(lodging, "execute", side_effect=execute),
            patch.object(lodging, "list_tariffs", return_value={"status": "ok", "areas": []}),
            patch("price_history.record_price_change") as record,
        ):
            lodging.save_tariff(
                {"areaUuid": lodging.AREAS[0]["uuid"], "listPrice": 12000},
                "JSESSIONID=admin",
            )
            record.assert_called()
            self.assertEqual(record.call_args.kwargs["department"], "accommodation")
            self.assertEqual(record.call_args.kwargs["old_price"], 10000.0)
            self.assertEqual(record.call_args.kwargs["new_price"], 12000)

        product_writes = [row for row in writes if row[0] == "product.product"]
        line_writes = [row for row in writes if row[0] == "sale.order.line"]
        self.assertTrue(product_writes)
        self.assertEqual(line_writes, [])
        self.assertEqual(stored[first_key][0]["price_unit"], 10000.0)

    def test_nurse_cannot_change_accommodation_prices(self) -> None:
        nurse = {"roles": ["Abikan:Nursing"], "privileges": ["app:adt"], "username": "nurse.abikan"}
        self.assertFalse(lodging._can_manage_tariffs(nurse))
        self.assertTrue(
            lodging._can_manage_tariffs(
                {"roles": ["Abikan:Hospital Admin"], "privileges": ["abikan:admin:staff"]}
            )
        )

    def test_nurse_can_view_accommodation_prices(self) -> None:
        nurse = {"roles": ["Abikan:Nursing"], "privileges": ["app:adt"], "username": "nurse.abikan"}
        with (
            patch.object(lodging, "require_session"),
            patch.object(lodging, "load_openmrs_user", return_value=nurse),
            patch.object(lodging, "odoo_reader", return_value=MagicMock()),
            patch.object(
                lodging,
                "ensure_accommodation_masters",
                return_value={"products": []},
            ),
            patch.object(
                lodging,
                "accommodation_currency",
                return_value=lodging.NGN_CURRENCY,
            ),
            patch.object(lodging, "find_accommodation_product", return_value={"list_price": 5000}),
        ):
            payload = lodging.list_tariffs("JSESSIONID=nurse")
        self.assertEqual(payload["status"], "ok")
        self.assertFalse(payload["canEdit"])
        self.assertTrue(payload["areas"])
        self.assertEqual(payload["areas"][0]["listPrice"]["amount"], 5000.0)

    def test_existing_sale_is_reused_and_not_repriced(self) -> None:
        line = {"price_unit": 10000.0, "external_order_id": "k1"}
        sale = {"name": "SO-OLD", "amount_total": 10000.0}
        with patch.object(lodging, "find_existing_sale", return_value=(line, sale)):
            reused_line, reused_sale, reused = lodging.create_posted_charge(
                MagicMock(),
                partner={"id": 4},
                product={"id": 88, "list_price": 12000},
                price=12000,
                key="k1",
                external_id="enc-1",
                name="Ward",
                origin="enc-1",
            )
        self.assertTrue(reused)
        self.assertEqual(reused_line["price_unit"], 10000.0)
        self.assertEqual(reused_sale["name"], "SO-OLD")


if __name__ == "__main__":
    unittest.main()

