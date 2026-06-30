"""Tests for the Flask app: the JSON payload, image serving by index, and the static shell, via the test client."""

from collections.abc import Callable, Sequence
from pathlib import Path

from charr.models import Verdict
from charr_review.data import SubstrateRecord, load_rows
from charr_review.server import create_app

MakeReview = Callable[[Sequence[SubstrateRecord]], tuple[Path, Path]]


def _record(rule_id: str = "has-title", image: str = "images/0001-has-title-fail-matplotlib.png") -> SubstrateRecord:
  return SubstrateRecord(manifest="labels", image=image, rule_id=rule_id, truth=Verdict.FAIL, predicted=Verdict.FAIL)


def test_api_rows_returns_the_substrate_as_json(make_review: MakeReview) -> None:
  substrate, dataset = make_review([_record()])
  client = create_app(load_rows(substrate, dataset), dataset).test_client()
  response = client.get("/api/rows")
  assert response.status_code == 200
  body = response.get_json()
  assert body["rows"][0]["rule_id"] == "has-title"
  assert "summary" in body
  assert "warnings" in body


def test_img_serves_the_chart_bytes_with_a_png_content_type(make_review: MakeReview) -> None:
  substrate, dataset = make_review([_record()])
  data = load_rows(substrate, dataset)
  client = create_app(data, dataset).test_client()
  response = client.get("/img/0")
  assert response.status_code == 200
  assert response.mimetype == "image/png"
  assert response.data == (dataset / data.rows[0].image).read_bytes()


def test_img_returns_404_for_an_out_of_range_index(make_review: MakeReview) -> None:
  substrate, dataset = make_review([_record()])
  client = create_app(load_rows(substrate, dataset), dataset).test_client()
  assert client.get("/img/999").status_code == 404


def test_img_returns_404_when_the_image_is_missing(make_review: MakeReview) -> None:
  substrate, dataset = make_review([_record()])
  data = load_rows(substrate, dataset)
  for image in (dataset / "images").iterdir():
    image.unlink()
  client = create_app(data, dataset).test_client()
  assert client.get("/img/0").status_code == 404


def test_root_serves_the_single_page_shell(make_review: MakeReview) -> None:
  substrate, dataset = make_review([_record()])
  client = create_app(load_rows(substrate, dataset), dataset).test_client()
  response = client.get("/")
  assert response.status_code == 200
  assert b"Charr review" in response.data


def test_static_asset_is_served(make_review: MakeReview) -> None:
  substrate, dataset = make_review([_record()])
  client = create_app(load_rows(substrate, dataset), dataset).test_client()
  assert client.get("/static/app.js").status_code == 200
