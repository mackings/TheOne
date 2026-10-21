from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_uow
from app.identity.api import schemas
from app.identity.application import customers
from app.identity.domain.entities import Customer

router = APIRouter(prefix="/customers", tags=["customers"])


def customer_out(c: Customer) -> schemas.CustomerOut:
    t, iris = c.template, c.iris_template
    return schemas.CustomerOut(
        id=c.id, external_id=c.external_id, display_name=c.display_name, language=c.language, created_at=c.created_at,
        enrolled=t is not None, template=schemas.TemplateOut.model_validate(t, from_attributes=True) if t else None,
        iris_enrolled=iris is not None,
        iris_template=schemas.IrisTemplateOut.model_validate(iris, from_attributes=True) if iris else None,
        iris_duress_enrolled=c.iris_duress is not None,
    )


@router.post("", response_model=schemas.CustomerOut, status_code=201)
def create_customer(body: schemas.CustomerCreate, uow=Depends(get_uow)):
    return customer_out(customers.create(uow, body.display_name, body.external_id, body.language))


@router.get("", response_model=list[schemas.CustomerOut])
def list_customers(uow=Depends(get_uow)):
    return [customer_out(c) for c in customers.all_customers(uow)]


@router.get("/{customer_id}", response_model=schemas.CustomerOut)
def get_customer(customer_id: str, uow=Depends(get_uow)):
    return customer_out(customers.load(uow, customer_id))


@router.get("/{customer_id}/events", response_model=list[schemas.EventOut])
def list_events(customer_id: str, limit: int = 50, uow=Depends(get_uow)):
    return [schemas.EventOut.model_validate(e, from_attributes=True) for e in customers.events(uow, customer_id, limit)]


@router.delete("/{customer_id}/template", status_code=204)
def revoke_template(customer_id: str, uow=Depends(get_uow)):
    """Revoke a customer's voice template. Required for consent withdrawal."""
    customers.revoke_voice(uow, customer_id)


@router.delete("/{customer_id}/iris-template", status_code=204)
def revoke_iris_template(customer_id: str, uow=Depends(get_uow)):
    customers.revoke_iris(uow, customer_id)


@router.delete("/{customer_id}/iris-duress-template", status_code=204)
def revoke_iris_duress(customer_id: str, uow=Depends(get_uow)):
    customers.revoke_iris_duress(uow, customer_id)
