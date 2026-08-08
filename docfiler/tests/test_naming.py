from docfiler.models import DocMetadata
from docfiler.naming import base_filename, slugify


def test_slugify_lowercases_and_replaces_punctuation():
    assert slugify("Home Depot - lumber & screws!") == "home-depot-lumber-screws"


def test_slugify_empty_falls_back_to_untitled():
    assert slugify("   !!!  ") == "untitled"


def test_base_filename_prefers_vendor_over_type():
    meta = DocMetadata(type="receipt", title="Lumber and screws", date="2026-08-08", vendor="Home Depot")
    assert base_filename(meta) == "2026-08-08_home-depot_lumber-and-screws"


def test_base_filename_falls_back_to_type_without_vendor():
    meta = DocMetadata(type="medical", title="Annual checkup", date="2026-08-08")
    assert base_filename(meta) == "2026-08-08_medical_annual-checkup"
