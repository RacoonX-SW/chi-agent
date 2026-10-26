from __future__ import annotations

import asyncio
import datetime as dt
import dataclasses
import gzip
import json
import multiprocessing
import os
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import b_provider_profile as profiles
import b_execution_policy as policies
import b_live_preflight as preflight

try:
    import httpx
    import b_provider_transport as transport
    import model_runner_adapter as runner_adapter
except ModuleNotFoundError as exc:
    httpx = transport = runner_adapter = None
    _OPTIONAL_IMPORT_ERROR = exc
else:
    _OPTIONAL_IMPORT_ERROR = None


def _hold_journal(root: str, run_id: str, acquired, release, results):
    try:
        journal = transport.SyntheticJournal(Path(root), run_id)
    except transport.GuardFailure as exc:
        results.put(exc.code)
        return
    results.put("acquired")
    acquired.set()
    release.wait(10)
    journal.finish(success=False)
    journal.close()


def _lock_handoff(root: str, acquired, close_old, old_closed, done, results):
    journal = transport.SyntheticJournal(Path(root), "first-owner")
    journal.finish(success=False)
    results.put("first-released")
    acquired.set()
    close_old.wait(10)
    journal.close()
    old_closed.set()
    done.wait(10)


def _evaluation_attempt_worker(root: str, run_id: str, acquired, release, results):
    try:
        journal = transport.EvaluationJournal(
            Path(root), run_id, evaluation_id="eval-contended", task_id="task-a", attempt_id="attempt-1",
            policy=policies.make_evaluation_policy("record_only"),
            profile=profiles.load_profile(today=dt.date(2026, 10, 26)),
        )
    except transport.GuardFailure as exc:
        results.put(exc.code)
        return
    results.put("acquired")
    acquired.set()
    release.wait(10)
    journal.finish(success=False)
    journal.close()


class ProfileReadOnlyTests(unittest.TestCase):
    def test_profile_source_and_documented_bounds_are_available_without_model_sdk(self):
        profile = profiles.load_profile(today=dt.date(2026, 10, 26))
        self.assertEqual(profile.model, "deepseek-flash")
        self.assertEqual(profile.input_reserve_tokens, 1_048_576)
        self.assertNotIn("budget", profile.raw)

    def test_plan_and_preflight_report_optional_sdk_missing_without_import_traceback(self):
        with patch.object(preflight, "_source_and_sdk", side_effect=preflight.PreparationFailure("sdk_package_missing")):
            plan = preflight.build_plan()
            status = preflight.build_preflight()
        self.assertEqual(plan["identity"]["status"], "unavailable")
        self.assertEqual(plan["identity"]["safe_error_code"], "sdk_package_missing")
        self.assertEqual(status["readiness"], "blocked_or_unknown")
        self.assertEqual(status["identity"]["safe_error_code"], "sdk_package_missing")


_HTTPX_TRANSPORT_BASE = httpx.AsyncBaseTransport if httpx is not None else object


@unittest.skipIf(transport is None, f"optional model dependencies unavailable: {_OPTIONAL_IMPORT_ERROR}")
class ProviderProfileAndTransportTests(unittest.TestCase):
    def test_prepared_profile_is_source_pinned_fresh_and_uses_documented_bounds(self):
        profile = profiles.load_profile(today=dt.date(2026, 10, 26))
        self.assertEqual(profile.model, "deepseek-flash")
        self.assertEqual(profile.endpoint, "https://api.deepseek.com")
        self.assertEqual(profile.input_reserve_tokens, 1_048_576)
        self.assertEqual(profile.input_price, Decimal("2"))
        self.assertEqual(profile.output_price, Decimal("8"))
        self.assertEqual(profile.raw["key_env"], "DEEPSEEK_API_KEY")
        with self.assertRaises(profiles.ProfileFailure):
            profiles.load_profile(today=dt.date(2026, 12, 1))

    def test_profile_price_or_input_bound_cannot_be_arbitrarily_changed(self):
        original = json.loads(profiles.PROFILE_PATH.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "profile.json"
            for field_path, value in ((("pricing", "input_peak_cache_miss_per_million"), 0.01),
                                      (("input_reservation", "tokens"), 1024),
                                      (("pricing", "source"), "https://example.invalid/cheap")):
                altered = json.loads(json.dumps(original))
                altered[field_path[0]][field_path[1]] = value
                path.write_text(json.dumps(altered), encoding="utf-8")
                with self.subTest(field=field_path), self.assertRaises(profiles.ProfileFailure):
                    profiles.load_profile(path, today=dt.date(2026, 10, 26))

    def test_verified_profile_runtime_fields_are_bound_to_pinned_raw_profile(self):
        profile = profiles.load_profile(today=dt.date(2026, 10, 26))
        for changed in (
            dataclasses.replace(profile, input_price=Decimal("0")),
            dataclasses.replace(profile, output_price=Decimal("0")),
            dataclasses.replace(profile, input_reserve_tokens=1),
            dataclasses.replace(profile, max_output_tokens=1),
            dataclasses.replace(profile, max_rounds=1),
        ):
            self.assertFalse(profiles.is_validated_profile(changed))

    def test_policy_identity_is_separate_and_runtime_fields_cannot_be_forged(self):
        local = policies.load_local_policy()
        self.assertEqual(local.scope, "local_development")
        self.assertEqual(local.hard_cap_cny, Decimal("5"))
        record = policies.make_evaluation_policy("record_only")
        capped = policies.make_evaluation_policy("capped", "7.5")
        self.assertIsNone(record.hard_cap_cny)
        self.assertEqual(capped.hard_cap_cny, Decimal("7.5"))
        self.assertNotEqual(record.sha256, capped.sha256)
        self.assertFalse(policies.is_validated_policy(dataclasses.replace(capped, hard_cap_cny=Decimal("5"))))
        for bad in (True, "NaN", "Infinity", "0", "-1", "1e9", 2):
            with self.subTest(cap=bad), self.assertRaises(policies.PolicyFailure):
                policies.make_evaluation_policy("capped", bad)

    def test_budget_evidence_missing_stale_and_bool_are_unknown(self):
        missing = profiles.validate_budget_evidence(None, today=dt.date(2026, 10, 26))
        self.assertEqual(missing["status"], "unknown")
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "budget.json"
            data = {"schema": "chi-shared-budget-evidence-v1", "scope": "shared_B_C",
                    "currency": "CNY", "prior_spend_cny": 1.25, "source": "local-reviewed-summary",
                    "checked_on": "2026-10-26"}
            path.write_text(json.dumps(data), encoding="utf-8")
            self.assertEqual(profiles.validate_budget_evidence(path, today=dt.date(2026, 10, 26))["status"], "known")
            data["prior_spend_cny"] = True
            path.write_text(json.dumps(data), encoding="utf-8")
            self.assertEqual(profiles.validate_budget_evidence(path, today=dt.date(2026, 10, 26))["status"], "unknown")
            data["prior_spend_cny"] = 1.25
            data["checked_on"] = "2026-01-01"
            path.write_text(json.dumps(data), encoding="utf-8")
            self.assertEqual(profiles.validate_budget_evidence(path, today=dt.date(2026, 10, 26))["status"], "unknown")
            data["checked_on"] = "2026-10-26"
            data["source"] = "synthetic-fixture"
            path.write_text(json.dumps(data), encoding="utf-8")
            self.assertEqual(profiles.validate_budget_evidence(path, today=dt.date(2026, 10, 26))["status"], "unknown")
            env_path = Path(temp) / ".env"
            env_path.write_text("DEEPSEEK_API_KEY=must-not-be-read", encoding="utf-8")
            with patch.object(Path, "read_text", side_effect=AssertionError(".env read")):
                self.assertEqual(profiles.validate_budget_evidence(env_path)["status"], "unknown")

    def test_read_only_preflight_checks_next_conservative_reserve(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "budget.json"
            data = {"schema": "chi-shared-budget-evidence-v1", "scope": "shared_B_C",
                    "currency": "CNY", "prior_spend_cny": 4.9, "source": "reviewed-b-c-accounting",
                    "checked_on": "2026-10-26"}
            path.write_text(json.dumps(data), encoding="utf-8")
            output = preflight.build_preflight(path)
            self.assertEqual(output["budget"]["status"], "known")
            self.assertEqual(output["budget"]["next_request_reserve_status"],
                             "insufficient_for_next_max_request_upper_bound")
            self.assertEqual(output["readiness"], "blocked_or_unknown")

    def test_plan_preflight_and_live_are_read_only_and_never_check_credentials(self):
        with tempfile.TemporaryDirectory() as temp:
            runs = Path(temp) / "must-not-exist"
            with patch.object(preflight, "SYNTHETIC_RUNS", runs):
                plan = preflight.build_plan()
                status = preflight.build_preflight()
                self.assertFalse(runs.exists())
                self.assertEqual(plan["budget"]["prior_spend"], "unknown")
                self.assertEqual(status["budget"]["status"], "unknown")
                self.assertEqual(plan["profile"]["auth_state"], "unverified")
                self.assertEqual(plan["side_effects"]["credentials_read"], False)
                with patch.object(preflight, "load_profile", side_effect=AssertionError("live must not inspect profile")):
                    self.assertEqual(preflight.main(["live"]), 2)
                self.assertFalse(runs.exists())

    def test_read_only_entry_reports_missing_optional_sdk_without_traceback(self):
        missing = preflight.PreparationFailure("sdk_package_missing")
        with patch.object(preflight, "_source_and_sdk", side_effect=missing):
            plan = preflight.build_plan()
            status = preflight.build_preflight()
        self.assertEqual(plan["identity"]["safe_error_code"], "sdk_package_missing")
        self.assertEqual(status["readiness"], "blocked_or_unknown")
        self.assertEqual(status["identity"]["safe_error_code"], "sdk_package_missing")

    def test_guard_blocks_bad_route_before_lower_transport(self):
        profile = profiles.load_profile(today=dt.date(2026, 10, 26))
        lower = _CountingTransport(httpx.Response(200, json={}))
        with tempfile.TemporaryDirectory() as temp:
            journal = transport.SyntheticJournal(Path(temp), "bad-route")
            guard = transport.GuardedTransport(profile=profile, journal=journal, lower=lower,
                                                ledger=runner_adapter.Ledger("success"), cap_cny=Decimal("5"),
                                                validate_response=lambda _payload: None,
                                                allowed_tool_names={"synthetic_lookup", "synthetic_format"})
            request = _request(url="https://user@api.deepseek.com/v1/chat/completions")
            with self.assertRaises(transport.GuardFailure) as error:
                asyncio.run(guard.handle_async_request(request))
            self.assertEqual(error.exception.code, "route_invalid")
            self.assertEqual(lower.calls, 0)
            journal.finish(success=False)
            journal.close()

    def test_guard_revalidates_profile_before_accepting_an_injected_transport(self):
        profile = profiles.load_profile(today=dt.date(2026, 10, 26))
        profile.raw["pricing"]["input_peak_cache_miss_per_million"] = 0.01
        lower = _CountingTransport(httpx.Response(200, json={}))
        with tempfile.TemporaryDirectory() as temp:
            journal = transport.SyntheticJournal(Path(temp), "changed-profile")
            with self.assertRaises(transport.GuardFailure) as error:
                transport.GuardedTransport(profile=profile, journal=journal, lower=lower,
                                           ledger=runner_adapter.Ledger("success"), cap_cny=Decimal("5"),
                                           validate_response=lambda _payload: None,
                                           allowed_tool_names={"synthetic_lookup", "synthetic_format"})
            self.assertEqual(error.exception.code, "profile_untrusted_or_stale")
            self.assertEqual(lower.calls, 0)
            journal.finish(success=False)
            journal.close()

    def test_guard_rejects_arbitrary_or_nonfinite_cap_before_any_send(self):
        profile = profiles.load_profile(today=dt.date(2026, 10, 26))
        lower = _CountingTransport(httpx.Response(200, json={}))
        with tempfile.TemporaryDirectory() as temp:
            journal = transport.SyntheticJournal(Path(temp), "bad-cap")
            for cap in (Decimal("10"), Decimal("Infinity"), Decimal("0")):
                with self.subTest(cap=cap), self.assertRaises(transport.GuardFailure):
                    transport.GuardedTransport(profile=profile, journal=journal, lower=lower,
                                               ledger=runner_adapter.Ledger("success"), cap_cny=cap,
                                               validate_response=lambda _payload: None,
                                               allowed_tool_names={"synthetic_lookup", "synthetic_format"})
            self.assertEqual(lower.calls, 0)
            journal.finish(success=False)
            journal.close()

    def test_guard_rejects_streaming_multiple_completions_and_ambiguous_limits_pre_send(self):
        profile = profiles.load_profile(today=dt.date(2026, 10, 26))
        for name, extra, code in (
            ("stream", {"stream": True}, "generation_shape_unsupported"),
            ("stream-options", {"stream_options": {"include_usage": True}}, "generation_shape_unsupported"),
            ("multiple", {"n": 2}, "generation_shape_unsupported"),
            ("fractional-one", {"n": 1.0}, "generation_shape_unsupported"),
            ("other-limit", {"max_completion_tokens": 64}, "generation_limit_ambiguous"),
            ("server-tool", {"tools": [{"type": "web_search"}]}, "tool_schema_not_allowlisted"),
            ("route-in-body", {"endpoint": "https://api.deepseek.com"}, "route_wire_separation_invalid"),
        ):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                lower = _CountingTransport(httpx.Response(200, json={}))
                journal = transport.SyntheticJournal(Path(temp), "unsupported")
                guard = transport.GuardedTransport(profile=profile, journal=journal, lower=lower,
                                                    ledger=runner_adapter.Ledger("success"), cap_cny=Decimal("5"),
                                                    validate_response=lambda _payload: None,
                                                    allowed_tool_names={"synthetic_lookup", "synthetic_format"})
                with self.assertRaises(transport.GuardFailure) as error:
                    asyncio.run(guard.handle_async_request(_request(extra=extra)))
                self.assertEqual(error.exception.code, code)
                self.assertEqual(lower.calls, 0)
                journal.finish(success=False)
                journal.close()

    def test_journal_write_failure_blocks_lower_transport(self):
        profile = profiles.load_profile(today=dt.date(2026, 10, 26))
        lower = _CountingTransport(httpx.Response(200, json={}))
        with tempfile.TemporaryDirectory() as temp:
            journal = transport.SyntheticJournal(Path(temp), "write-failure")
            guard = transport.GuardedTransport(profile=profile, journal=journal, lower=lower,
                                                ledger=runner_adapter.Ledger("success"), cap_cny=Decimal("5"),
                                                validate_response=lambda _payload: None,
                                                allowed_tool_names={"synthetic_lookup", "synthetic_format"})
            with patch.object(transport, "_atomic_replace", side_effect=OSError("not persisted")):
                with self.assertRaises(transport.GuardFailure) as error:
                    asyncio.run(guard.handle_async_request(_request()))
            self.assertEqual(error.exception.code, "journal_write_failed")
            self.assertEqual(lower.calls, 0)
            journal.close()

    def test_effect_persistence_failure_stops_before_next_sdk_request(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "synthetic"
            with patch.object(preflight, "SYNTHETIC_RUNS", root), patch.object(
                transport.SyntheticJournal, "record_effect", side_effect=transport.GuardFailure("journal_write_failed", "tool_execution")
            ):
                journal, ledger, result = asyncio.run(preflight._rehearse("success", "effect-write-failure"))
            self.assertIsNone(result)
            self.assertEqual(ledger.error_code, "journal_write_failed")
            self.assertEqual(ledger.transport_calls, 1)
            evidence = json.loads(journal.run_path.read_text(encoding="utf-8"))
            self.assertEqual(evidence["primary_error_code"], "journal_write_failed")

    def test_restart_cannot_clear_pending_and_new_run_id_cannot_spend(self):
        profile = profiles.load_profile(today=dt.date(2026, 10, 26))
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            journal = transport.SyntheticJournal(root, "interrupted")
            request = _request()
            body = json.loads(request.content)
            journal.reserve(profile, request, body, request.content, 128, 1)
            journal.close()
            stored = json.loads((root / "synthetic-accounting.json").read_text(encoding="utf-8"))
            self.assertEqual(stored["pending"]["status"], "pending")
            with self.assertRaises(transport.GuardFailure) as error:
                transport.SyntheticJournal(root, "new-run-id")
            self.assertIn(error.exception.code, {"synthetic_namespace_busy_or_pending", "synthetic_prior_pending_unknown"})

    def test_fresh_guard_cannot_overwrite_authoritative_pending_state(self):
        profile = profiles.load_profile(today=dt.date(2026, 10, 26))
        with tempfile.TemporaryDirectory() as temp:
            journal = transport.SyntheticJournal(Path(temp), "pending-authority")
            request = _request()
            journal.reserve(profile, request, json.loads(request.content), request.content, 128, 1)
            with self.assertRaises(transport.GuardFailure) as error:
                journal.reserve(profile, request, json.loads(request.content), request.content, 128, 1)
            self.assertEqual(error.exception.code, "synthetic_prior_pending_unknown")
            stored = json.loads(journal.state_path.read_text(encoding="utf-8"))
            self.assertEqual(stored["pending"]["run_id"], "pending-authority")
            journal.close()

    def test_released_or_closed_journal_cannot_bind_or_send_with_a_guard(self):
        profile = profiles.load_profile(today=dt.date(2026, 10, 26))
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = transport.SyntheticJournal(root, "finished-owner")
            first.finish(success=False)
            second = transport.SyntheticJournal(root, "current-owner")
            lower = _CountingTransport(httpx.Response(200, json={}))
            for label in ("released", "closed"):
                if label == "closed":
                    first.close()
                with self.subTest(state=label), self.assertRaises(transport.GuardFailure) as error:
                    transport.GuardedTransport(profile=profile, journal=first, lower=lower,
                                               ledger=runner_adapter.Ledger("success"), cap_cny=Decimal("5"),
                                               validate_response=lambda _payload: None,
                                               allowed_tool_names={"synthetic_lookup", "synthetic_format"})
                self.assertEqual(error.exception.code, "journal_lock_not_owned")
                self.assertEqual(lower.calls, 0)
            second.finish(success=False)
            second.close()

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = transport.SyntheticJournal(root, "guarded-owner")
            lower = _CountingTransport(httpx.Response(200, json={}))
            guard = transport.GuardedTransport(profile=profile, journal=first, lower=lower,
                                               ledger=runner_adapter.Ledger("success"), cap_cny=Decimal("5"),
                                               validate_response=lambda _payload: None,
                                               allowed_tool_names={"synthetic_lookup", "synthetic_format"})
            first.finish(success=False)
            first.close()
            second = transport.SyntheticJournal(root, "replacement-owner")
            with self.assertRaises(transport.GuardFailure) as error:
                asyncio.run(guard.handle_async_request(_request()))
            self.assertEqual(error.exception.code, "journal_lock_not_owned")
            self.assertEqual(lower.calls, 0)
            second.finish(success=False)
            second.close()

    def test_lock_fd_close_failure_persists_incomplete_terminal_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            journal = transport.SyntheticJournal(Path(temp), "close-failure")
            journal.mark_error("prior_primary_error")
            lock_fd = journal.lock_fd
            original_close = os.close

            def close_except_lock(fd):
                if fd == lock_fd:
                    raise OSError("synthetic close failure")
                return original_close(fd)

            with patch.object(transport.os, "close", side_effect=close_except_lock):
                with self.assertRaises(transport.GuardFailure) as error:
                    journal.finish(success=False)
            self.assertEqual(error.exception.code, "namespace_lock_release_failed")
            evidence = json.loads(journal.run_path.read_text(encoding="utf-8"))
            self.assertEqual(evidence["state"], "incomplete")
            self.assertEqual(evidence["primary_error_code"], "prior_primary_error")
            self.assertEqual(evidence["cleanup_error_code"], "namespace_lock_release_failed")
            self.assertEqual(evidence["persistence_error_code"], "namespace_lock_release_failed")
            self.assertNotEqual(evidence["state"], "complete")
            original_close(lock_fd)

    def test_missing_shared_journal_cannot_reset_prior_spend_from_other_run_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = transport.SyntheticJournal(root, "first-complete")
            first.finish(success=True)
            first.close()
            (root / "synthetic-accounting.json").unlink()
            with self.assertRaises(transport.GuardFailure) as error:
                transport.SyntheticJournal(root, "attempted-reset")
            self.assertEqual(error.exception.code, "synthetic_journal_missing")
            self.assertTrue((root / "first-complete.json").exists())

    def test_legacy_or_bool_money_state_fails_closed_without_rewrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "old-complete.json").write_text("{}", encoding="utf-8")
            path = root / "synthetic-accounting.json"
            original = json.dumps({
                "schema": "chi-b-synthetic-accounting-v1", "namespace": "synthetic",
                "prior_spend_cny": "0.2", "prior_source": "synthetic-rehearsal-prior-v1",
                "known_settled_cost_cny": "0.3", "pending": None,
                "known_input_tokens": 3, "known_output_tokens": 4, "usage_complete": True,
            })
            path.write_text(original, encoding="utf-8")
            with self.assertRaises(transport.GuardFailure):
                transport.SyntheticJournal(root, "must-not-migrate")
            self.assertEqual(path.read_text(encoding="utf-8"), original)

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            journal = transport.SyntheticJournal(root, "valid-seed")
            journal.finish(success=False)
            journal.close()
            path = root / "synthetic-accounting.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["prior_spend_cny"] = True
            original = json.dumps(data)
            path.write_text(original, encoding="utf-8")
            with self.assertRaises(transport.GuardFailure):
                transport.SyntheticJournal(root, "bool-money")
            self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_actual_official_runner_and_sdk_use_generic_guard_for_three_turn_rehearsal(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "synthetic"
            with patch.object(preflight, "SYNTHETIC_RUNS", root):
                journal, ledger, result = asyncio.run(preflight._rehearse("success", "three-turn"))
            self.assertIsNotNone(result)
            self.assertEqual(ledger.transport_calls, 3)
            self.assertEqual(len(ledger.effects), 2)
            evidence = json.loads(journal.run_path.read_text(encoding="utf-8"))
            self.assertEqual(evidence["state"], "complete")
            self.assertEqual(evidence["metadata"]["provider_profile"]["input_reservation"]["measurement"], "documented_not_measured")
            self.assertEqual(evidence["metadata"]["real_budget_status"], "unknown")
            self.assertEqual(evidence["real_cost_cny"], None)
            self.assertEqual([x["status"] for x in evidence["requests"]], ["settled"] * 3)
            self.assertEqual(evidence["requests"][0]["route"], "https://api.deepseek.com/v1/chat/completions")
            self.assertEqual(evidence["requests"][0]["input_reserve_tokens"], 1_048_576)
            first_body = ledger.requests[0]["body"]
            self.assertEqual(first_body["model"], "deepseek-flash")
            self.assertEqual(first_body["reasoning_effort"], "high")
            self.assertEqual(first_body["thinking"], {"type": "enabled"})
            self.assertNotIn("endpoint", first_body)
            self.assertNotIn("key_env", first_body)
            self.assertEqual([item["call_id"] for item in ledger.tool_exchanges], ["call-1", "call-1", "call-2"])

    def test_second_request_budget_exhaustion_keeps_first_effect_and_sends_once(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "synthetic"
            with patch.object(preflight, "SYNTHETIC_RUNS", root):
                journal, ledger, result = asyncio.run(preflight._rehearse(
                    "success", "second-budget", initial_prior=Decimal("2.90178"),
                    synthetic_cap=Decimal("5"), output_tokens=128,
                ))
            self.assertIsNone(result)
            self.assertEqual(ledger.transport_calls, 1)
            self.assertEqual(ledger.error_code, "budget_exhausted")
            self.assertEqual(len(ledger.effects), 1)
            evidence = json.loads(journal.run_path.read_text(encoding="utf-8"))
            self.assertEqual(evidence["requests"][0]["status"], "settled")
            self.assertEqual(evidence["state"], "incomplete")

    def test_evaluation_record_only_completes_above_local_five_cny(self):
        policy = policies.make_evaluation_policy("record_only")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "evaluation"
            with patch.object(preflight, "EVALUATION_RUNS", root):
                journal, ledger, result = asyncio.run(preflight._rehearse(
                    "evaluation-over-five", "record-only-run", policy=policy,
                    evaluation_id="eval-record", task_id="task-a", attempt_id="attempt-1",
                ))
            evidence = json.loads(journal.run_path.read_text(encoding="utf-8"))
            self.assertIsNotNone(result)
            self.assertEqual(ledger.transport_calls, 3)
            self.assertEqual(evidence["state"], "complete")
            self.assertGreater(Decimal(evidence["accounting"]["aggregate_cost_upper_cny"]), Decimal("5"))
            self.assertEqual(evidence["execution_policy"]["mode"], "record_only")
            self.assertEqual(evidence["accounting"]["aggregate_cost_upper_cny"], "6.196608")
            self.assertIsNone(evidence["real_usage"])
            self.assertIsNone(evidence["real_cost_cny"])
            self.assertIsNone(evidence["official_reward"])

    def test_evaluation_capped_stops_before_third_request_and_keeps_effects(self):
        policy = policies.make_evaluation_policy("capped", "5")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "evaluation"
            with patch.object(preflight, "EVALUATION_RUNS", root):
                journal, ledger, result = asyncio.run(preflight._rehearse(
                    "evaluation-over-five", "capped-run", policy=policy,
                    evaluation_id="eval-capped", task_id="task-a", attempt_id="attempt-1",
                ))
            evidence = json.loads(journal.run_path.read_text(encoding="utf-8"))
            self.assertIsNone(result)
            self.assertEqual(ledger.transport_calls, 2)
            self.assertEqual(ledger.error_code, "budget_exhausted")
            self.assertEqual(len(evidence["effects"]), 2)
            self.assertEqual(evidence["state"], "incomplete")

    def test_evaluation_attempts_are_independent_but_unknown_attempt_is_not_replayed(self):
        policy = policies.make_evaluation_policy("record_only")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "evaluation"
            with patch.object(preflight, "EVALUATION_RUNS", root):
                first, first_ledger, first_result = asyncio.run(preflight._rehearse(
                    "missing-usage", "unknown-run", policy=policy, evaluation_id="eval-isolation",
                    task_id="task-a", attempt_id="attempt-1",
                ))
                second, second_ledger, second_result = asyncio.run(preflight._rehearse(
                    "success", "other-run", policy=policy, evaluation_id="eval-isolation",
                    task_id="task-b", attempt_id="attempt-1",
                ))
            first_evidence_before = first.run_path.read_bytes()
            self.assertIsNone(first_result)
            self.assertFalse(first_ledger.usage_complete)
            self.assertEqual(first_ledger.transport_calls, 1)
            self.assertIsNotNone(second_result)
            self.assertEqual(second_ledger.transport_calls, 3)
            self.assertEqual(json.loads(first_evidence_before)["state"], "unknown")

            with patch.object(preflight, "EVALUATION_RUNS", root), patch.object(
                    runner_adapter, "_run_offline", new=AsyncMock(side_effect=AssertionError("runner entered"))) as run:
                with self.assertRaises(preflight.PreparationFailure) as error:
                    asyncio.run(preflight._rehearse(
                        "success", "replacement-run", policy=policy, evaluation_id="eval-isolation",
                        task_id="task-a", attempt_id="attempt-1",
                    ))
            self.assertIn(error.exception.code, {"evaluation_attempt_path_conflict", "evaluation_attempt_claim_exists"})
            run.assert_not_awaited()
            self.assertEqual(first.run_path.read_bytes(), first_evidence_before)

    def test_evaluation_registry_rejects_policy_change_for_same_evaluation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "evaluation"
            record = policies.make_evaluation_policy("record_only")
            capped = policies.make_evaluation_policy("capped", "4")
            with patch.object(preflight, "EVALUATION_RUNS", root):
                asyncio.run(preflight._rehearse("success", "first", policy=record,
                                                evaluation_id="eval-bound", task_id="task-a", attempt_id="a1"))
                with patch.object(runner_adapter, "_run_offline", new=AsyncMock(side_effect=AssertionError("runner entered"))) as run:
                    with self.assertRaises(preflight.PreparationFailure) as error:
                        asyncio.run(preflight._rehearse("success", "second", policy=capped,
                                                        evaluation_id="eval-bound", task_id="task-b", attempt_id="a1"))
            self.assertEqual(error.exception.code, "evaluation_policy_conflict")
            run.assert_not_awaited()

    def test_two_processes_cannot_claim_same_evaluation_attempt(self):
        with tempfile.TemporaryDirectory() as temp:
            ctx = multiprocessing.get_context("spawn")
            acquired, release = ctx.Event(), ctx.Event()
            results = ctx.Queue()
            first = ctx.Process(target=_evaluation_attempt_worker,
                                args=(temp, "process-one", acquired, release, results))
            first.start()
            self.assertTrue(acquired.wait(10))
            self.assertEqual(results.get(timeout=10), "acquired")
            second_acquired, second_release = ctx.Event(), ctx.Event()
            second = ctx.Process(target=_evaluation_attempt_worker,
                                 args=(temp, "process-two", second_acquired, second_release, results))
            second.start()
            second.join(10)
            self.assertFalse(second.is_alive())
            self.assertEqual(results.get(timeout=10), "evaluation_attempt_path_conflict")
            release.set()
            first.join(10)
            self.assertFalse(first.is_alive())

    def test_evaluation_preflight_does_not_require_or_read_development_budget(self):
        policy = policies.make_evaluation_policy("record_only")
        with patch.object(preflight, "_source_and_sdk", side_effect=preflight.PreparationFailure("sdk_package_missing")):
            plan = preflight.build_plan(policy)
            status = preflight.build_preflight(policy=policy)
            with self.assertRaises(preflight.PreparationFailure) as error:
                preflight.build_preflight(Path("/must/not/read.json"), policy=policy)
        self.assertEqual(error.exception.code, "development_budget_not_applicable")
        self.assertEqual(plan["budget"]["status"], "not_read")
        self.assertEqual(status["budget"]["status"], "not_read")
        self.assertEqual(status["readiness"], "identified_evaluation_policy_rehearsal_not_frozen")

    def test_known_over_limit_usage_is_settled_before_stopping(self):
        for scenario in ("over-profile-output", "over-document-context"):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as temp:
                root = Path(temp) / "synthetic"
                with patch.object(preflight, "SYNTHETIC_RUNS", root):
                    journal, ledger, result = asyncio.run(preflight._rehearse(scenario, "over-limit"))
                self.assertIsNone(result)
                self.assertEqual(ledger.transport_calls, 1)
                self.assertEqual(ledger.error_code, "returned_usage_over_limit")
                self.assertTrue(ledger.usage_complete)
                evidence = json.loads(journal.run_path.read_text(encoding="utf-8"))
                self.assertEqual(evidence["requests"][0]["status"], "settled")
                self.assertIsNotNone(evidence["accounting"]["aggregate_usage"])
                self.assertEqual(evidence["state"], "incomplete")

    def test_http_and_network_errors_have_one_send_and_keep_unknown_pending(self):
        for scenario, code in (("http-429", "http_rate_limited"), ("http-503", "http_unavailable"),
                               ("timeout", "transport_timeout"), ("connect-error", "transport_connect_error")):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as temp:
                root = Path(temp) / "synthetic"
                with patch.object(preflight, "SYNTHETIC_RUNS", root):
                    journal, ledger, result = asyncio.run(preflight._rehearse(scenario, "one-send"))
                self.assertIsNone(result)
                self.assertEqual(ledger.transport_calls, 1)
                self.assertEqual(ledger.error_code, code)
                evidence = json.loads(journal.run_path.read_text(encoding="utf-8"))
                self.assertEqual(evidence["state"], "unknown")
                state = json.loads((root / "synthetic-accounting.json").read_text(encoding="utf-8"))
                self.assertEqual(state["pending"]["status"], "unknown")

    def test_post_tool_http_error_keeps_settled_effect_without_retry_or_replay(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "synthetic"
            with patch.object(preflight, "SYNTHETIC_RUNS", root):
                journal, ledger, result = asyncio.run(preflight._rehearse("post-tool-503", "post-tool-failure"))
            self.assertIsNone(result)
            self.assertEqual(ledger.transport_calls, 2)
            self.assertEqual(ledger.error_code, "http_unavailable")
            self.assertEqual(ledger.effects, [{"tool": "synthetic_lookup", "call_id": "call-1",
                                               "result": "synthetic-value"}])
            evidence = json.loads(journal.run_path.read_text(encoding="utf-8"))
            self.assertEqual(evidence["state"], "unknown")
            self.assertEqual(evidence["effects"], ledger.effects)

    def test_invalid_repeated_call_id_stops_before_second_effect_or_third_send(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "synthetic"
            with patch.object(preflight, "SYNTHETIC_RUNS", root):
                journal, ledger, result = asyncio.run(preflight._rehearse("duplicate-call-id", "dup-id"))
            self.assertIsNone(result)
            self.assertEqual(ledger.transport_calls, 2)
            self.assertEqual(ledger.error_code, "tool_call_id_invalid")
            self.assertEqual(len(ledger.effects), 1)
            evidence = json.loads(journal.run_path.read_text(encoding="utf-8"))
            self.assertEqual(evidence["effects"], ledger.effects)
            self.assertEqual(evidence["accounting"]["usage_complete"], True)

    def test_usage_breakdown_must_be_consistent_and_reasoning_is_not_added_twice(self):
        use = transport.GuardedTransport._usage
        self.assertEqual(use({"usage": {"prompt_tokens": 16, "completion_tokens": 10, "total_tokens": 26,
                                         "prompt_tokens_details": {"cached_tokens": 0},
                                         "prompt_cache_hit_tokens": 0, "prompt_cache_miss_tokens": 16}}), (16, 10))
        self.assertEqual(use({"usage": {"prompt_tokens": 16, "completion_tokens": 10, "total_tokens": 26,
                                         "prompt_tokens_details": {"cached_tokens": 5}}}), (16, 10))
        self.assertEqual(use({"usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15,
                                         "prompt_cache_hit_tokens": 4, "prompt_cache_miss_tokens": 6,
                                         "completion_tokens_details": {"reasoning_tokens": 3}}}), (10, 5))
        for usage in (
            {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 16},
            {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15,
             "prompt_cache_hit_tokens": 4, "prompt_cache_miss_tokens": 5},
            {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15,
             "prompt_cache_hit_tokens": None, "prompt_cache_miss_tokens": None},
            {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15,
             "prompt_tokens_details": {"cached_tokens": 2},
             "prompt_cache_hit_tokens": 3, "prompt_cache_miss_tokens": 7},
            {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15,
             "completion_tokens_details": {"reasoning_tokens": 6}},
        ):
            with self.subTest(usage=usage), self.assertRaises(transport.GuardFailure):
                use({"usage": usage})

    def test_usage_total_context_ceiling_accounts_before_stopping(self):
        profile = profiles.load_profile(today=dt.date(2026, 10, 26))
        payload = {"usage": {"prompt_tokens": 1_048_575, "completion_tokens": 2,
                             "total_tokens": 1_048_577}}
        lower = _CountingTransport(httpx.Response(200, json=payload))
        with tempfile.TemporaryDirectory() as temp:
            journal = transport.SyntheticJournal(Path(temp), "total-context-over")
            ledger = runner_adapter.Ledger("success")
            guard = transport.GuardedTransport(profile=profile, journal=journal, lower=lower, ledger=ledger,
                                               cap_cny=Decimal("5"), validate_response=lambda _payload: None,
                                               allowed_tool_names={"synthetic_lookup", "synthetic_format"})
            with self.assertRaises(transport.GuardFailure) as error:
                asyncio.run(guard.handle_async_request(_request()))
            self.assertEqual(error.exception.code, "returned_usage_over_limit")
            self.assertEqual(lower.calls, 1)
            self.assertTrue(ledger.usage_complete)
            self.assertEqual(journal.run_doc["requests"][0]["status"], "settled")
            journal.finish(success=False)
            journal.close()

    def test_gzip_response_is_not_decoded_twice(self):
        profile = profiles.load_profile(today=dt.date(2026, 10, 26))
        payload = {"usage": {"prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17}}
        wire = gzip.compress(json.dumps(payload).encode("utf-8"))

        class GzipTransport(httpx.AsyncBaseTransport):
            calls = 0

            async def handle_async_request(self, request):
                self.calls += 1
                return httpx.Response(200, headers={"content-encoding": "gzip"}, content=wire, request=request)

            async def aclose(self):
                return None

        lower = GzipTransport()
        with tempfile.TemporaryDirectory() as temp:
            journal = transport.SyntheticJournal(Path(temp), "gzip-response")
            guard = transport.GuardedTransport(profile=profile, journal=journal, lower=lower,
                                               ledger=runner_adapter.Ledger("success"), cap_cny=Decimal("5"),
                                               validate_response=lambda _payload: None,
                                               allowed_tool_names={"synthetic_lookup", "synthetic_format"})
            response = asyncio.run(guard.handle_async_request(_request()))
            self.assertEqual(response.json(), payload)
            self.assertEqual(lower.calls, 1)
            journal.finish(success=False)
            journal.close()

    def test_cli_run_identity_is_exclusive_before_official_runner(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "synthetic"
            with patch.object(preflight, "SYNTHETIC_RUNS", root):
                self.assertEqual(preflight.main(["rehearse", "--run-id", "cli-once"]), 0)
                evidence_path = root / "cli-once.json"
                original = evidence_path.read_bytes()
                with patch.object(runner_adapter, "_run_offline", new=AsyncMock()) as run:
                    self.assertEqual(preflight.main(["rehearse", "--run-id", "cli-once"]), 2)
                    run.assert_not_awaited()
                self.assertEqual(evidence_path.read_bytes(), original)
                self.assertEqual(preflight.main(["rehearse", "--run-id", "../unsafe"]), 2)

    def test_actual_processes_cannot_both_acquire_synthetic_namespace(self):
        context = multiprocessing.get_context("spawn")
        with tempfile.TemporaryDirectory() as temp:
            acquired = context.Event()
            release = context.Event()
            results = context.Queue()
            first = context.Process(target=_hold_journal, args=(temp, "process-one", acquired, release, results))
            first.start()
            self.assertTrue(acquired.wait(10))
            second = context.Process(target=_hold_journal, args=(temp, "process-two", acquired, release, results))
            second.start()
            first_result = results.get(timeout=10)
            second_result = results.get(timeout=10)
            release.set()
            first.join(10)
            second.join(10)
            self.assertEqual(sorted((first_result, second_result)), ["acquired", "synthetic_namespace_busy_or_pending"])
            self.assertEqual(first.exitcode, 0)
            self.assertEqual(second.exitcode, 0)

    def test_old_process_close_cannot_unlink_new_flock_owner(self):
        context = multiprocessing.get_context("spawn")
        with tempfile.TemporaryDirectory() as temp:
            released, close_old, old_closed, done = (context.Event() for _ in range(4))
            results = context.Queue()
            first = context.Process(target=_lock_handoff, args=(temp, released, close_old, old_closed, done, results))
            first.start()
            self.assertTrue(released.wait(10))
            self.assertEqual(results.get(timeout=10), "first-released")
            second = transport.SyntheticJournal(Path(temp), "second-owner")
            close_old.set()
            self.assertTrue(old_closed.wait(10))
            with self.assertRaises(transport.GuardFailure) as error:
                transport.SyntheticJournal(Path(temp), "third-owner")
            self.assertEqual(error.exception.code, "synthetic_namespace_busy_or_pending")
            second.finish(success=False)
            second.close()
            done.set()
            first.join(10)
            self.assertEqual(first.exitcode, 0)


class _CountingTransport(_HTTPX_TRANSPORT_BASE):
    def __init__(self, response: httpx.Response):
        self.response = response
        self.calls = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        return httpx.Response(self.response.status_code, json=self.response.json(), request=request)

    async def aclose(self) -> None:
        return None


def _request(*, url: str = "https://api.deepseek.com/v1/chat/completions",
             extra: dict | None = None) -> httpx.Request:
    body = {"model": "deepseek-flash", "max_tokens": 128, "reasoning_effort": "high",
            "thinking": {"type": "enabled"}, "messages": []}
    body.update(extra or {})
    return httpx.Request("POST", url, content=json.dumps(body).encode())


if __name__ == "__main__":
    unittest.main()
