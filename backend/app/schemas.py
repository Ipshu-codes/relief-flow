from pydantic import BaseModel, Field


class ContributionCreate(BaseModel):
    donor_name: str = Field(min_length=1, max_length=120)
    is_anonymous: bool = False
    amount_npr: float = Field(gt=0, le=100000000)
    txn_id: str = Field(min_length=3, max_length=80)
    channel: str = Field(pattern='^(esewa|khalti|bank|other)$')