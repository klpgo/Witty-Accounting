from pydantic import BaseModel


class PricingResult(BaseModel):
    read: int
    priced: int
    missing_price: int
    invalid_energy: int
    skipped_invoiced: int
