"""The Flask app that serves the review SPA: one JSON payload, the chart images, and the static assets.

The whole substrate is handed to the browser once as JSON (small, text); navigation, filtering, and prefetching happen
client-side, and images are the only on-demand fetch (docs/adr/0023). Image requests are resolved by row index against
the dataset root, never from a client-supplied path, so the server cannot be coaxed into serving files outside it.
"""

import webbrowser
from pathlib import Path

from flask import Flask, abort, jsonify, send_file
from flask.typing import ResponseReturnValue

from charr_review.data import ReviewData, resolve_image_path

_STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(data: ReviewData, dataset_dir: Path) -> Flask:
  """Build the Flask app serving the review UI for one substrate.

  :param data: The loaded review rows, summary, and warnings.
  :param dataset_dir: The dataset root used to resolve each row's image.
  :return: The configured Flask application.
  """
  app = Flask(__name__, static_folder=None)
  payload = data.model_dump(mode="json")

  @app.get("/")
  def index() -> ResponseReturnValue:
    """Serve the single-page shell."""
    return send_file(_STATIC_DIR / "index.html")

  @app.get("/static/<path:name>")
  def asset(name: str) -> ResponseReturnValue:
    """Serve a bundled static asset, refusing any path that escapes the static directory."""
    target = (_STATIC_DIR / name).resolve()
    if not target.is_relative_to(_STATIC_DIR) or not target.is_file():
      abort(404)
    return send_file(target)

  @app.get("/api/rows")
  def rows() -> ResponseReturnValue:
    """Return the whole substrate as one JSON payload: rows, summary, and warnings."""
    return jsonify(payload)

  @app.get("/img/<int:index>")
  def image(index: int) -> ResponseReturnValue:
    """Serve the chart image for a row, resolved by index against the dataset root."""
    if not 0 <= index < len(data.rows):
      abort(404)
    path = resolve_image_path(dataset_dir, data.rows[index].image)
    if path is None:
      abort(404)
    return send_file(path, max_age=3600)

  return app


def serve(
  data: ReviewData,
  dataset_dir: Path,
  *,
  host: str = "127.0.0.1",
  port: int = 8000,
  open_browser: bool = True,
) -> None:
  """Serve the review UI, blocking until interrupted.

  :param data: The loaded review rows, summary, and warnings.
  :param dataset_dir: The dataset root used to resolve each row's image.
  :param host: The interface to bind; defaults to loopback.
  :param port: The TCP port to bind.
  :param open_browser: Whether to open a browser window at startup.
  """
  app = create_app(data, dataset_dir)
  if open_browser:
    webbrowser.open(f"http://{host}:{port}/")
  app.run(host=host, port=port, threaded=True)
