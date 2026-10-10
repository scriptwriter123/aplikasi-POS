from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AuthorizationError, ValidationError
from app.models import BulkPriceRule, Product, User


class BulkPricingService:
    def __init__(self, session: Session):
        self.session = session

    def rule_for_product(self, product_id: int) -> BulkPriceRule | None:
        return self.session.scalar(
            select(BulkPriceRule).where(
                BulkPriceRule.product_id == product_id
            )
        )

    def rules(self) -> list[BulkPriceRule]:
        return list(
            self.session.scalars(
                select(BulkPriceRule)
                .join(Product)
                .where(Product.deleted_at.is_(None))
                .order_by(Product.name, Product.sku)
            )
        )

    def save_rule(
        self,
        actor: User,
        product_id: int,
        quantity_threshold: int,
        discount_percent: Decimal,
        special_price: int,
        pricing_mode: str,
    ) -> BulkPriceRule:
        self._require_owner(actor)
        product = self.session.get(Product, product_id)
        if product is None or product.deleted_at is not None:
            raise ValidationError("Produk yang dipilih tidak ditemukan.")
        if quantity_threshold < 1:
            raise ValidationError("Batas qty harus minimal 1.")
        if product.selling_price <= 0:
            raise ValidationError(
                "Harga jual produk harus lebih dari Rp 0 untuk mengatur harga spesial."
            )
        if pricing_mode not in {"PRICE", "PERCENT"}:
            raise ValidationError("Pilih mekanisme harga spesial yang valid.")
        if pricing_mode == "PRICE":
            if special_price < 0 or special_price >= product.selling_price:
                raise ValidationError(
                    "Harga spesial harus minimal Rp 0 dan lebih rendah dari harga satuan."
                )
            percent = self.discount_percent_for_price(
                product.selling_price,
                special_price,
            )
            if percent <= 0:
                raise ValidationError(
                    "Selisih harga terlalu kecil untuk ditampilkan sebagai persentase."
                )
        else:
            percent = Decimal(discount_percent)
            if percent <= 0 or percent > 100:
                raise ValidationError(
                    "Potongan harga harus lebih dari 0% hingga 100%."
                )
            special_price = self.special_price(product.selling_price, percent)

        rule = self.rule_for_product(product_id)
        if rule is None:
            rule = BulkPriceRule(product_id=product_id)
            self.session.add(rule)
        rule.quantity_threshold = quantity_threshold
        rule.discount_percent = percent
        rule.special_price = special_price
        rule.pricing_mode = pricing_mode
        try:
            self.session.commit()
            self.session.refresh(rule)
        except Exception:
            self.session.rollback()
            raise
        return rule

    def delete_rule(self, actor: User, product_id: int) -> bool:
        self._require_owner(actor)
        rule = self.rule_for_product(product_id)
        if rule is None:
            return False
        try:
            self.session.delete(rule)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return True

    def unit_price(self, product: Product, quantity: int) -> int:
        rule = self.rule_for_product(product.id)
        if rule is None or quantity < rule.quantity_threshold:
            return product.selling_price
        if rule.pricing_mode == "PRICE":
            return rule.special_price
        discounted = Decimal(product.selling_price) * (
            Decimal("1") - Decimal(rule.discount_percent) / Decimal("100")
        )
        return int(discounted.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    @staticmethod
    def special_price(
        regular_price: int,
        discount_percent: Decimal,
    ) -> int:
        discounted = Decimal(regular_price) * (
            Decimal("1") - Decimal(discount_percent) / Decimal("100")
        )
        return int(discounted.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    @staticmethod
    def discount_percent_for_price(regular_price: int, special_price: int) -> Decimal:
        return (
            (Decimal(regular_price - special_price) * Decimal("100"))
            / Decimal(regular_price)
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def effective_special_price(
        self,
        product: Product,
        rule: BulkPriceRule,
    ) -> int:
        if rule.pricing_mode == "PRICE":
            return rule.special_price
        return self.special_price(product.selling_price, rule.discount_percent)

    @staticmethod
    def _require_owner(actor: User):
        if actor.role.name.upper() != "OWNER":
            raise AuthorizationError("Hanya OWNER yang dapat mengatur harga spesial.")
