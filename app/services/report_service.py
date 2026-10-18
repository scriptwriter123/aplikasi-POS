from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Product, Sale, SaleItem, User


class ReportService:
    def __init__(self, session: Session):
        self.session = session

    def sales(
        self,
        start: datetime,
        end: datetime,
        cashier_id: int | None = None,
    ) -> list[dict]:
        sales = self._sales_in_period(start, end, cashier_id)
        if not sales:
            return []

        sale_ids = [sale.id for sale, _ in sales]
        items_by_sale: dict[int, list[dict]] = {}
        item_statement = (
            select(SaleItem, Product.name, Product.sku)
            .join(Product, Product.id == SaleItem.product_id)
            .where(SaleItem.sale_id.in_(sale_ids))
            .order_by(SaleItem.sale_id, SaleItem.id)
        )
        for item, product_name, product_sku in self.session.execute(item_statement):
            items_by_sale.setdefault(item.sale_id, []).append(
                {
                    "product_name": product_name,
                    "product_sku": product_sku,
                    "quantity": item.qty,
                    "unit_price": item.unit_price,
                    "line_total": item.line_total,
                }
            )

        return [
            {
                "sale": sale,
                "invoice_no": sale.invoice_no,
                "created_at": sale.created_at,
                "cashier_name": cashier_name,
                "revenue": sale.grand_total,
                "items": items_by_sale.get(sale.id, []),
            }
            for sale, cashier_name in sales
        ]

    def profits(self, start: datetime, end: datetime) -> list[dict]:
        sales = self._sales_in_period(start, end)
        if not sales:
            return []

        items_by_sale: dict[int, list[SaleItem]] = {}
        items = self.session.scalars(
            select(SaleItem).where(
                SaleItem.sale_id.in_([sale.id for sale, _ in sales])
            )
        )
        for item in items:
            items_by_sale.setdefault(item.sale_id, []).append(item)

        rows = []
        for sale, cashier_name in sales:
            sale_items = items_by_sale.get(sale.id, [])
            missing_cost_count = sum(
                item.unit_cost is None for item in sale_items
            )
            if not sale_items:
                missing_cost_count = 1

            known_cost = sum(
                item.qty * item.unit_cost
                for item in sale_items
                if item.unit_cost is not None
            )
            known_profit = sum(
                item.line_total - item.qty * item.unit_cost
                for item in sale_items
                if item.unit_cost is not None
            )
            rows.append(
                {
                    "sale": sale,
                    "invoice_no": sale.invoice_no,
                    "created_at": sale.created_at,
                    "cashier_name": cashier_name,
                    "revenue": sale.grand_total,
                    "known_cost": known_cost,
                    "known_profit": known_profit,
                    "missing_cost_count": missing_cost_count,
                }
            )
        return rows

    def low_stock_products(self, threshold: int = 5) -> list[Product]:
        statement = (
            select(Product)
            .where(
                Product.deleted_at.is_(None),
                Product.is_active.is_(True),
                Product.stock_qty < threshold,
            )
            .order_by(Product.stock_qty, Product.name, Product.sku)
        )
        return list(self.session.scalars(statement))

    def sales_summary(self, period: str) -> list[dict]:
        """Rekap penjualan lunas dikelompokkan per hari/bulan/tahun."""
        if period not in {"day", "month", "year"}:
            raise ValueError(f"Jenis periode laporan tidak dikenal: {period}")
        statement = (
            select(Sale.created_at, Sale.grand_total)
            .where(Sale.status == "PAID")
            .order_by(Sale.created_at, Sale.id)
        )
        buckets: dict[str, dict] = {}
        for created_at, grand_total in self.session.execute(statement):
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            local = created_at.astimezone()
            if period == "day":
                key = local.strftime("%d-%m-%Y")
            elif period == "month":
                key = local.strftime("%m-%Y")
            else:
                key = str(local.year)
            bucket = buckets.setdefault(
                key,
                {"period": key, "transactions": 0, "revenue": 0},
            )
            bucket["transactions"] += 1
            bucket["revenue"] += int(grand_total)
        return list(reversed(list(buckets.values())))

    def inventory_valuation(self) -> list[dict]:
        """Nilai persediaan: stok x harga beli tiap barang (non-dihapus)."""
        statement = (
            select(Product)
            .where(Product.deleted_at.is_(None))
            .order_by(Product.sku)
        )
        return [
            {
                "sku": product.sku,
                "name": product.name,
                "stock_qty": product.stock_qty,
                "purchase_price": product.purchase_price,
                "value": product.stock_qty * product.purchase_price,
            }
            for product in self.session.scalars(statement)
        ]

    def _sales_in_period(
        self,
        start: datetime,
        end: datetime,
        cashier_id: int | None = None,
    ):
        if start >= end:
            raise ValueError("Waktu awal laporan harus sebelum waktu akhir.")

        start_utc = self._to_utc_naive(start)
        end_utc = self._to_utc_naive(end)
        conditions = [
            Sale.status == "PAID",
            Sale.created_at >= start_utc,
            Sale.created_at < end_utc,
        ]
        if cashier_id is not None:
            conditions.append(Sale.cashier_id == cashier_id)
        statement = (
            select(Sale, User.full_name)
            .join(User, User.id == Sale.cashier_id)
            .where(*conditions)
            .order_by(Sale.created_at, Sale.id)
        )
        return list(self.session.execute(statement))

    @staticmethod
    def _to_utc_naive(value: datetime) -> datetime:
        if value.tzinfo is None:
            value = value.astimezone()
        return value.astimezone(timezone.utc).replace(tzinfo=None)
