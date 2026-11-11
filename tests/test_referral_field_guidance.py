import pytest

from agents.tool import FunctionTool
import scripts.development.run_development_legacy as live
import chi_agent.referral_field_guidance as guidance


class Journal:
    def __init__(self):
        self.run_doc = {}
        self.persist_count = 0
    def _persist(self):
        self.persist_count += 1


async def callback(_context, _payload):
    return "synthetic result"


def tool(name, description="original"):
    schema = {"type": "object", "properties": {"setting": {"type": "string", "enum": ["alpha", "beta"]}},
              "required": ["setting"], "additionalProperties": False}
    return FunctionTool(name=name, description=description, params_json_schema=schema,
                        on_invoke_tool=callback, strict_json_schema=False)


@pytest.mark.parametrize("name", list(guidance.GUIDANCE))
def test_guidance_changes_only_description_and_records_hashes(name):
    journal = Journal()
    current = tool(name)
    schema, invoke, tool_name = current.params_json_schema, current.on_invoke_tool, current.name
    assert live._apply_referral_guidance(current, name, journal) is current
    assert current.name == tool_name and current.params_json_schema is schema and current.on_invoke_tool is invoke
    assert current.description.count(guidance.MARKER) == 1
    record = journal.run_doc["referral_field_guidance"]
    assert record["version"] == guidance.VERSION and record["guidance_sha256"] == guidance.GUIDANCE_SHA256
    assert record["tools"][name] == {"guidance_sha256": guidance.sha256(guidance.GUIDANCE[name]),
                                    "original_description_sha256": guidance.sha256("original"),
                                    "appended_description_sha256": guidance.sha256(current.description)}
    again = tool(name)
    live._apply_referral_guidance(again, name, journal)
    assert again.description == current.description and journal.persist_count == 1
    with pytest.raises(live.LiveFailure, match="referral_guidance_description_invalid"):
        live._apply_referral_guidance(current, name, journal)
    with pytest.raises(live.LiveFailure, match="referral_guidance_identity_conflict"):
        live._apply_referral_guidance(tool(name, "changed"), name, journal)


def test_unrelated_tool_and_old_identity_are_untouched():
    import chi_agent.evaluation_bundle as evaluation_bundle
    import chi_agent.evaluation_cli as evaluation_entry
    journal = Journal()
    current = tool("chart.search_patients")
    assert live._apply_referral_guidance(current, current.name, journal) is current
    assert current.description == "original" and journal.run_doc == {} and journal.persist_count == 0
    assert "src/chi_agent/referral_field_guidance.py" in live._execution_identity(k=True)["application_files_sha256"]
    assert "src/chi_agent/referral_field_guidance.py" not in live._execution_identity()["application_files_sha256"]
    assert "scripts/chi_agent/referral_field_guidance.py" not in evaluation_bundle.PACKAGE_FILES
    assert "scripts/chi_agent/referral_field_guidance.py" not in evaluation_entry.ENTRY_RUNTIME_SOURCE_FILES
