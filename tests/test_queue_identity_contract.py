import ast
from dataclasses import asdict, replace
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys
import unittest
from unittest import mock

from tests.test_unattended_job_queue import job, queue


class QueueIdentityTests(unittest.TestCase):
    def test_version_and_schema(self):
        d = queue.get_queue_identity()
        self.assertEqual(d.to_dict(), dict(identity_version="0.1", queue_id="data-lab-unattended-main",
            identity_status="CONFIGURED", reason_code="POLICY_BACKED_LOGICAL_IDENTITY"))

    def test_valid(self):
        self.assertTrue(queue.validate_queue_identity(queue.get_queue_identity()))

    def test_recreation(self):
        first, second = queue.get_queue_identity(), queue.get_queue_identity()
        self.assertIsNot(first, second)
        self.assertEqual(first, second)

    def test_module_restart_equivalent(self):
        name = "queue_identity_restart_fixture"
        spec = importlib.util.spec_from_file_location(name, queue.__file__)
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(sys.modules, {name: module}):
            spec.loader.exec_module(module)
            self.assertEqual(module.get_queue_identity().to_dict(), queue.get_queue_identity().to_dict())

    def test_no_host_process_path_environment_clock_sources(self):
        with mock.patch("os.getcwd", side_effect=AssertionError()), \
             mock.patch("os.getpid", side_effect=AssertionError()), \
             mock.patch("socket.gethostname", side_effect=AssertionError()), \
             mock.patch("pathlib.Path.resolve", side_effect=AssertionError()), \
             mock.patch("builtins.open", side_effect=AssertionError()), \
             mock.patch.object(queue, "datetime") as clock, \
             mock.patch.dict(os.environ, {"QUEUE_ID": "not-authorized", "PUSHOVER_APP_TOKEN": "fixture-only"}):
            self.assertTrue(queue.validate_queue_identity(queue.get_queue_identity()))
            clock.now.assert_not_called()

    def test_source_has_no_external_dependencies(self):
        tree = ast.parse(Path(queue.__file__).read_text(encoding="utf-8"))
        factory = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "get_queue_identity")
        self.assertEqual([n.func.id for n in ast.walk(factory) if isinstance(n, ast.Call)], ["QueueIdentity"])
        imports = {n.module if isinstance(n, ast.ImportFrom) else n.names[0].name
                   for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))}
        self.assertEqual(imports, {"__future__", "dataclasses", "datetime", "re", "typing"})

    def test_validation_read_only(self):
        d = queue.get_queue_identity()
        before = json.dumps(d.to_dict())
        for _ in range(3):
            self.assertTrue(queue.validate_queue_identity(d))
            self.assertEqual(before, json.dumps(d.to_dict()))
        with self.assertRaises(AttributeError):
            d.queue_id = "other"

    def test_direct_construction_not_authentication(self):
        d = queue.QueueIdentity(**queue.get_queue_identity().to_dict())
        self.assertTrue(queue.validate_queue_identity(d))

    def test_no_queue_mutation_or_decision_changes(self):
        jobs = [job(requires_approval=True, state=queue.WAITING_APPROVAL)]
        before = [asdict(j) for j in jobs]
        idle = queue.select_next_job(jobs)
        blocked = queue.assess_queue_blocked(jobs)
        queue.validate_queue_identity(queue.get_queue_identity())
        self.assertEqual(before, [asdict(j) for j in jobs])
        self.assertEqual(idle, queue.select_next_job(jobs))
        self.assertTrue(blocked.blocked)
        self.assertTrue(queue.validate_queue_blocked_decision(blocked))
        self.assertNotIn("queue_id", blocked.to_dict())
        self.assertEqual(len(blocked.to_dict()), 7)

    def test_unapproved_second_queue_rejected(self):
        d = replace(queue.get_queue_identity(), queue_id="another-logical-queue")
        self.assertFalse(queue.validate_queue_identity(d))

    def test_malformed_objects(self):
        for value in (None, {}, [], "data-lab-unattended-main", queue.get_queue_identity().to_dict()):
            self.assertFalse(queue.validate_queue_identity(value))


def invalid(change):
    def test(self):
        self.assertFalse(queue.validate_queue_identity(replace(queue.get_queue_identity(), **change)))
    return test


for name, change in {
    "version": {"identity_version": "2"}, "empty": {"queue_id": ""},
    "space": {"queue_id": "data lab"}, "path": {"queue_id": "C:/queue"},
    "url": {"queue_id": "https://queue"}, "secret": {"queue_id": "secret-token"},
    "unicode": {"queue_id": "キュー"}, "newline": {"queue_id": "data-lab-unattended-main\n"},
    "case": {"queue_id": "DATA-LAB-UNATTENDED-MAIN"}, "none": {"queue_id": None},
    "list": {"queue_id": []}, "status": {"identity_status": "INFERRED"},
    "source": {"reason_code": "HOSTNAME_DERIVED"}, "bool_version": {"identity_version": True},
}.items():
    setattr(QueueIdentityTests, "test_reject_" + name, invalid(change))


if __name__ == "__main__":
    unittest.main()
