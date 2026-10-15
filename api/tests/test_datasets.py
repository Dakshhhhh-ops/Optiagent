from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from optiagent_api.datasets import DatasetStore
from optiagent_api.main import app
from optiagent_api.routers.datasets import get_store

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_store(engine: Engine) -> Iterator[DatasetStore]:
    store = DatasetStore(engine, max_file_bytes=2_000, max_files=3)
    app.dependency_overrides[get_store] = lambda: store
    yield store
    app.dependency_overrides.clear()


def test_list_samples() -> None:
    samples = client.get("/api/v1/datasets/samples").json()
    assert {s["id"] for s in samples} >= {"sunray", "ta_labs", "india_distribution"}


def test_sample_end_to_end() -> None:
    created = client.post("/api/v1/datasets/samples/sunray")
    assert created.status_code == 201
    detail = created.json()
    dataset_id = detail["meta"]["id"]
    assert {t["name"] for t in detail["tables"]} == {"costs.csv", "mills.csv", "silos.csv"}

    suggestion = client.post(
        f"/api/v1/datasets/{dataset_id}/suggest", json={"kind": "transportation"}
    ).json()
    assert suggestion["mapping"]["costs"]["layout"] == "matrix"

    built = client.post(f"/api/v1/datasets/{dataset_id}/build", json=suggestion["mapping"]).json()
    assert built["problem"]["kind"] == "transportation"

    solved = client.post("/api/v1/solve", json=built["problem"]).json()
    assert solved["result"]["objective"] == 435
    assert solved["verified"] is True


def test_upload_and_build_reports_issues() -> None:
    files = [
        ("files", ("costs.csv", b"plant,C1\nP1,two", "text/csv")),
        ("files", ("supply.csv", b"plant,cap\nP1,5", "text/csv")),
        ("files", ("demand.csv", b"city,need\nC1,5", "text/csv")),
    ]
    detail = client.post("/api/v1/datasets", files=files).json()
    dataset_id = detail["meta"]["id"]
    assert [f["original"] for f in detail["meta"]["files"]] == [
        "costs.csv",
        "supply.csv",
        "demand.csv",
    ]

    mapping = {
        "kind": "transportation",
        "costs": {"layout": "matrix", "table": "costs.csv", "row_id_column": "plant"},
        "supply": {"table": "supply.csv", "id_column": "plant", "value_column": "cap"},
        "demand": {"table": "demand.csv", "id_column": "city", "value_column": "need"},
    }
    built = client.post(f"/api/v1/datasets/{dataset_id}/build", json=mapping).json()
    assert built["problem"] is None
    [error] = [i for i in built["issues"] if i["severity"] == "error"]
    assert (error["table"], error["row"], error["column"]) == ("costs.csv", 2, "C1")


def test_upload_rejects_bad_files() -> None:
    bad_type = client.post("/api/v1/datasets", files=[("files", ("x.pdf", b"%PDF", "x"))])
    assert bad_type.status_code == 422
    assert "unsupported" in bad_type.text

    too_big = client.post(
        "/api/v1/datasets", files=[("files", ("x.csv", b"a,b\n" + b"1,2\n" * 1000, "text/csv"))]
    )
    assert too_big.status_code == 422
    assert "larger than" in too_big.text

    too_many = client.post(
        "/api/v1/datasets",
        files=[("files", (f"f{i}.csv", b"a\n1", "text/csv")) for i in range(4)],
    )
    assert too_many.status_code == 422


def test_file_names_are_stripped_of_paths() -> None:
    for name in ("../../evil.csv", r"..\..\evil.csv", "/etc/evil.csv"):
        detail = client.post(
            "/api/v1/datasets", files=[("files", (name, b"a,b\n1,2", "text/csv"))]
        ).json()
        assert detail["meta"]["files"][0]["original"] == "evil.csv", name
        assert [t["name"] for t in detail["tables"]] == ["evil.csv"]


def test_unknown_or_malformed_dataset_id() -> None:
    assert client.get("/api/v1/datasets/" + "0" * 32).status_code == 404
    assert client.get("/api/v1/datasets/..%2F..%2Fetc").status_code == 404
    assert (
        client.post("/api/v1/datasets/abc/suggest", json={"kind": "assignment"}).status_code == 404
    )


def test_download_sample_template() -> None:
    import io
    import zipfile

    response = client.get("/api/v1/datasets/samples/sunray/download")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    names = zipfile.ZipFile(io.BytesIO(response.content)).namelist()
    assert sorted(names) == ["costs.csv", "mills.csv", "silos.csv"]
    assert client.get("/api/v1/datasets/samples/nope/download").status_code == 404
