"""Doctor and laboratory directories."""

from typing import TypeVar

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Doctor, Lab, MedicalRecord
from app.schemas import DoctorIn, DoctorOut, LabIn, LabOut
from app.security import private_dependencies

router = APIRouter(prefix="/api", tags=["directories"], dependencies=private_dependencies)

T = TypeVar("T")


def _counts(db: Session, column) -> dict[str, int]:
    rows = db.execute(select(column, func.count()).where(column.is_not(None)).group_by(column)).all()
    return {key: count for key, count in rows}


def _get_or_404(db: Session, model: type[T], item_id: str, label: str) -> T:
    item = db.get(model, item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{label} not found")
    return item


def _doctor_out(doctor: Doctor, count: int) -> DoctorOut:
    out = DoctorOut.model_validate(doctor)
    out.record_count = count
    return out


def _lab_out(lab: Lab, count: int) -> LabOut:
    out = LabOut.model_validate(lab)
    out.record_count = count
    return out


# ---------------------------------------------------------------- doctors


@router.get("/doctors", response_model=list[DoctorOut])
def list_doctors(
    q: str | None = Query(default=None, max_length=100), db: Session = Depends(get_db)
) -> list[DoctorOut]:
    stmt = select(Doctor).order_by(func.lower(Doctor.name))
    if q and q.strip():
        term = q.strip()
        stmt = stmt.where(
            Doctor.name.icontains(term, autoescape=True)
            | Doctor.specialization.icontains(term, autoescape=True)
            | Doctor.hospital.icontains(term, autoescape=True)
        )
    counts = _counts(db, MedicalRecord.doctor_id)
    return [_doctor_out(d, counts.get(d.id, 0)) for d in db.scalars(stmt).all()]


@router.post("/doctors", response_model=DoctorOut, status_code=status.HTTP_201_CREATED)
def create_doctor(payload: DoctorIn, db: Session = Depends(get_db)) -> DoctorOut:
    doctor = Doctor(**payload.model_dump())
    db.add(doctor)
    db.commit()
    return _doctor_out(doctor, 0)


@router.get("/doctors/{doctor_id}", response_model=DoctorOut)
def get_doctor(doctor_id: str, db: Session = Depends(get_db)) -> DoctorOut:
    doctor = _get_or_404(db, Doctor, doctor_id, "Doctor")
    return _doctor_out(doctor, _counts(db, MedicalRecord.doctor_id).get(doctor.id, 0))


@router.put("/doctors/{doctor_id}", response_model=DoctorOut)
def update_doctor(doctor_id: str, payload: DoctorIn, db: Session = Depends(get_db)) -> DoctorOut:
    doctor = _get_or_404(db, Doctor, doctor_id, "Doctor")
    for key, value in payload.model_dump().items():
        setattr(doctor, key, value)
    db.commit()
    return _doctor_out(doctor, _counts(db, MedicalRecord.doctor_id).get(doctor.id, 0))


@router.delete("/doctors/{doctor_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_doctor(doctor_id: str, db: Session = Depends(get_db)) -> Response:
    doctor = _get_or_404(db, Doctor, doctor_id, "Doctor")
    used = _counts(db, MedicalRecord.doctor_id).get(doctor.id, 0)
    if used:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This doctor is used by {used} record{'s' if used != 1 else ''}. "
            "Change or delete those records first.",
        )
    db.delete(doctor)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------- laboratories


@router.get("/labs", response_model=list[LabOut])
def list_labs(q: str | None = Query(default=None, max_length=100), db: Session = Depends(get_db)) -> list[LabOut]:
    stmt = select(Lab).order_by(func.lower(Lab.name))
    if q and q.strip():
        stmt = stmt.where(Lab.name.icontains(q.strip(), autoescape=True))
    counts = _counts(db, MedicalRecord.lab_id)
    return [_lab_out(x, counts.get(x.id, 0)) for x in db.scalars(stmt).all()]


@router.post("/labs", response_model=LabOut, status_code=status.HTTP_201_CREATED)
def create_lab(payload: LabIn, db: Session = Depends(get_db)) -> LabOut:
    lab = Lab(**payload.model_dump())
    db.add(lab)
    db.commit()
    return _lab_out(lab, 0)


@router.get("/labs/{lab_id}", response_model=LabOut)
def get_lab(lab_id: str, db: Session = Depends(get_db)) -> LabOut:
    lab = _get_or_404(db, Lab, lab_id, "Laboratory")
    return _lab_out(lab, _counts(db, MedicalRecord.lab_id).get(lab.id, 0))


@router.put("/labs/{lab_id}", response_model=LabOut)
def update_lab(lab_id: str, payload: LabIn, db: Session = Depends(get_db)) -> LabOut:
    lab = _get_or_404(db, Lab, lab_id, "Laboratory")
    for key, value in payload.model_dump().items():
        setattr(lab, key, value)
    db.commit()
    return _lab_out(lab, _counts(db, MedicalRecord.lab_id).get(lab.id, 0))


@router.delete("/labs/{lab_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lab(lab_id: str, db: Session = Depends(get_db)) -> Response:
    lab = _get_or_404(db, Lab, lab_id, "Laboratory")
    used = _counts(db, MedicalRecord.lab_id).get(lab.id, 0)
    if used:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This laboratory is used by {used} record{'s' if used != 1 else ''}. "
            "Change or delete those records first.",
        )
    db.delete(lab)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
