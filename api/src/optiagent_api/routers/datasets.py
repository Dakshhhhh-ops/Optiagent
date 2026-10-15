import io
import zipfile
from typing import Annotated, Literal

from fastapi import APIRouter, Body, Depends, File, HTTPException, Response, UploadFile
from pydantic import BaseModel

from optiagent_api.datasets import DatasetError, DatasetMeta, DatasetStore
from optiagent_api.db import get_engine
from optiagent_api.settings import get_settings
from optiagent_core.examples import SampleDataset, list_sample_datasets, sample_dataset_files
from optiagent_core.ingest import (
    AssignmentMapping,
    DataIssue,
    Suggestion,
    Table,
    TableProfile,
    TransportationMapping,
    load_problem,
    profile_table,
    suggest_mapping,
)
from optiagent_core.schema import AssignmentProblem, TransportationProblem

router = APIRouter(prefix="/api/v1/datasets", tags=["datasets"])


def get_store() -> DatasetStore:
    s = get_settings()
    return DatasetStore(get_engine(s.database_url), s.max_upload_bytes, s.max_upload_files)


StoreDep = Annotated[DatasetStore, Depends(get_store)]


class DatasetDetail(BaseModel):
    meta: DatasetMeta
    tables: list[TableProfile]


class SuggestRequest(BaseModel):
    kind: Literal["transportation", "assignment"]


class BuildResponse(BaseModel):
    problem: TransportationProblem | AssignmentProblem | None
    issues: list[DataIssue]


def _detail(store: DatasetStore, meta: DatasetMeta) -> DatasetDetail:
    return DatasetDetail(meta=meta, tables=[profile_table(t) for t in store.tables(meta.id)])


def _tables(store: DatasetStore, dataset_id: str) -> list[Table]:
    try:
        return store.tables(dataset_id)
    except KeyError:
        raise HTTPException(404, f"unknown dataset {dataset_id!r}") from None


@router.get("/samples", response_model=list[SampleDataset])
def samples() -> list[SampleDataset]:
    return list_sample_datasets()


@router.get(
    "/samples/{sample_id}/download",
    responses={200: {"content": {"application/zip": {}}}},
    response_class=Response,
)
def download_sample(sample_id: str) -> Response:
    """The sample's files as a .zip, to use as a template for your own data."""
    try:
        files = sample_dataset_files(sample_id)
    except KeyError:
        raise HTTPException(404, f"unknown sample {sample_id!r}") from None
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files:
            archive.writestr(name, data)
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{sample_id}-template.zip"'},
    )


@router.post("/samples/{sample_id}", response_model=DatasetDetail, status_code=201)
def create_from_sample(sample_id: str, store: StoreDep) -> DatasetDetail:
    try:
        files = sample_dataset_files(sample_id)
    except KeyError:
        raise HTTPException(404, f"unknown sample {sample_id!r}") from None
    return _detail(store, store.create(files, source=f"sample:{sample_id}"))


@router.post("", response_model=DatasetDetail, status_code=201)
async def upload(files: Annotated[list[UploadFile], File()], store: StoreDep) -> DatasetDetail:
    payload = []
    for f in files:
        # Read one byte past the limit so oversized files are rejected without loading them fully.
        data = await f.read(store.max_file_bytes + 1)
        payload.append((f.filename or "upload", data))
    try:
        meta = store.create(payload)
    except DatasetError as exc:
        raise HTTPException(422, str(exc)) from None
    return _detail(store, meta)


@router.get("/{dataset_id}", response_model=DatasetDetail)
def get_dataset(dataset_id: str, store: StoreDep) -> DatasetDetail:
    try:
        meta = store.meta(dataset_id)
    except KeyError:
        raise HTTPException(404, f"unknown dataset {dataset_id!r}") from None
    return _detail(store, meta)


@router.post("/{dataset_id}/suggest", response_model=Suggestion)
def suggest(dataset_id: str, request: SuggestRequest, store: StoreDep) -> Suggestion:
    return suggest_mapping(_tables(store, dataset_id), request.kind)


@router.post("/{dataset_id}/build", response_model=BuildResponse)
def build(
    dataset_id: str,
    mapping: Annotated[TransportationMapping | AssignmentMapping, Body(discriminator="kind")],
    store: StoreDep,
) -> BuildResponse:
    result = load_problem(_tables(store, dataset_id), mapping)
    return BuildResponse(problem=result.problem, issues=result.issues)
