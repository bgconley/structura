from pathlib import Path

import yaml

from lib.uploads.models import UploadAttempt, UploadCreate, UploadDecision
from lib.uploads.policy import UploadPolicyRead


def test_upload_public_schemas_match_runtime_models_exactly():
    contract = yaml.safe_load(Path("contracts/api/openapi.yaml").read_text())
    actual = contract["components"]["schemas"]
    expected = {}
    for model in (UploadCreate, UploadDecision, UploadAttempt, UploadPolicyRead):
        schema = model.model_json_schema(by_alias=True, ref_template="#/components/schemas/{model}")
        expected.update(schema.pop("$defs", {}))
        expected[model.__name__] = schema
    for key, value in expected.items():
        assert actual[key] == value, key
