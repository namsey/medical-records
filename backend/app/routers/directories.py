"""Doctor and laboratory directories."""

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.models import Doctor, Lab
from app.schemas import DoctorIn, DoctorOut, LabIn, LabOut
from app.security import private_dependencies
from app.services.record_store import RecordStore, get_record_store

router = APIRouter(prefix="/api", tags=["directories"], dependencies=private_dependencies)


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
    q: str | None = Query(default=None, max_length=100), store: RecordStore = Depends(get_record_store)
) -> list[DoctorOut]:
    counts = store.doctor_record_counts()
    return [_doctor_out(d, counts.get(d.id, 0)) for d in store.list_doctors(q)]


@router.post("/doctors", response_model=DoctorOut, status_code=status.HTTP_201_CREATED)
def create_doctor(payload: DoctorIn, store: RecordStore = Depends(get_record_store)) -> DoctorOut:
    return _doctor_out(store.create_doctor(payload.model_dump()), 0)


@router.get("/doctors/{doctor_id}", response_model=DoctorOut)
def get_doctor(doctor_id: str, store: RecordStore = Depends(get_record_store)) -> DoctorOut:
    doctor = store.get_doctor(doctor_id)
    return _doctor_out(doctor, store.doctor_record_counts().get(doctor.id, 0))


@router.put("/doctors/{doctor_id}", response_model=DoctorOut)
def update_doctor(doctor_id: str, payload: DoctorIn, store: RecordStore = Depends(get_record_store)) -> DoctorOut:
    doctor = store.update_item(store.get_doctor(doctor_id), payload.model_dump())
    return _doctor_out(doctor, store.doctor_record_counts().get(doctor.id, 0))


@router.delete("/doctors/{doctor_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_doctor(doctor_id: str, store: RecordStore = Depends(get_record_store)) -> Response:
    doctor = store.get_doctor(doctor_id)
    used = store.doctor_record_counts().get(doctor.id, 0)
    if used:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This doctor is used by {used} record{'s' if used != 1 else ''}. "
            "Change or delete those records first.",
        )
    store.delete_item(doctor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------- laboratories


@router.get("/labs", response_model=list[LabOut])
def list_labs(q: str | None = Query(default=None, max_length=100), store: RecordStore = Depends(get_record_store)) -> list[LabOut]:
    counts = store.lab_record_counts()
    return [_lab_out(x, counts.get(x.id, 0)) for x in store.list_labs(q)]


@router.post("/labs", response_model=LabOut, status_code=status.HTTP_201_CREATED)
def create_lab(payload: LabIn, store: RecordStore = Depends(get_record_store)) -> LabOut:
    return _lab_out(store.create_lab(payload.model_dump()), 0)


@router.get("/labs/{lab_id}", response_model=LabOut)
def get_lab(lab_id: str, store: RecordStore = Depends(get_record_store)) -> LabOut:
    lab = store.get_lab(lab_id)
    return _lab_out(lab, store.lab_record_counts().get(lab.id, 0))


@router.put("/labs/{lab_id}", response_model=LabOut)
def update_lab(lab_id: str, payload: LabIn, store: RecordStore = Depends(get_record_store)) -> LabOut:
    lab = store.update_item(store.get_lab(lab_id), payload.model_dump())
    return _lab_out(lab, store.lab_record_counts().get(lab.id, 0))


@router.delete("/labs/{lab_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lab(lab_id: str, store: RecordStore = Depends(get_record_store)) -> Response:
    lab = store.get_lab(lab_id)
    used = store.lab_record_counts().get(lab.id, 0)
    if used:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This laboratory is used by {used} record{'s' if used != 1 else ''}. "
            "Change or delete those records first.",
        )
    store.delete_item(lab)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
