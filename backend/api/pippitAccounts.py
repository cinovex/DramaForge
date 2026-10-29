"""Local encrypted Pippit account configuration; keys never leave read responses."""
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from database import get_db
from models.drama import pippitAccountRecord
from services.crypto import encrypt

router = APIRouter(prefix="/api/pippit/accounts", tags=["pippit-accounts"])

class AccountRequest(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    apiKey: str = Field(default="", max_length=4096)
    enabled: bool = True
    resetCredits: bool = False

def publicAccount(account):
    return {"id": account.id, "label": account.label, "enabled": bool(account.enabled), "exhausted": bool(account.exhausted), "configured": bool(account.api_key_enc) or account.id == "default"}

def ensureDefaultAccount(db):
    if not db.get(pippitAccountRecord, "default"):
        db.add(pippitAccountRecord(id="default", label="原有本机授权账号", api_key_enc="", enabled=1, exhausted=0)); db.commit()

@router.get("")
def listAccounts(db: Session = Depends(get_db)):
    ensureDefaultAccount(db)
    return [publicAccount(account) for account in db.query(pippitAccountRecord).order_by(pippitAccountRecord.created_at).all()]

@router.post("")
def addAccount(body: AccountRequest, db: Session = Depends(get_db)):
    if not body.apiKey.strip(): raise HTTPException(422, "请输入该账号的 Pippit API Key")
    account = pippitAccountRecord(id=str(uuid4()), label=body.label.strip(), api_key_enc=encrypt(body.apiKey.strip()), enabled=int(body.enabled), exhausted=0)
    db.add(account); db.commit()
    return publicAccount(account)

@router.put("/{accountId}")
def updateAccount(accountId: str, body: AccountRequest, db: Session = Depends(get_db)):
    account = db.get(pippitAccountRecord, accountId)
    if not account: raise HTTPException(404, "账号不存在")
    account.label = body.label.strip()
    account.enabled = int(body.enabled)
    if body.apiKey.strip(): account.api_key_enc = encrypt(body.apiKey.strip()); account.exhausted = 0
    if body.resetCredits: account.exhausted = 0
    db.commit()
    return publicAccount(account)
