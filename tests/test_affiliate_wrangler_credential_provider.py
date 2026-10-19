"""Synthetic executables and captured fake output only; never real Wrangler/auth."""
from contextlib import redirect_stdout, redirect_stderr
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import affiliate_wrangler_credential_provider as subject
from affiliate_d1_sensitive_query import D1QueryClient
import revenue_mvp_expansion_initial_revalidation as initial

TOKEN="synthetic-not-a-real-credential"


class WranglerCredentialProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.node=self.root/"node.exe"
        self.cli=self.root/"wrangler/bin/wrangler.js"
        self.bundle=self.root/"wrangler/wrangler-dist/cli.js"
        self.package=self.root/"wrangler/package.json"
        for path,value in ((self.node,b"SYNTHETIC_NODE_NOT_EXECUTABLE"),(self.cli,b"SYNTHETIC_ENTRY"),(self.bundle,b"SYNTHETIC_BUNDLE")):
            path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(value)
        self.package.write_text(json.dumps({"name":"wrangler","version":"4.151.1"}),encoding="utf-8")
        self.environment={"PATH":"synthetic-path","WRANGLER_WRITE_LOGS":"true",
                          "WRANGLER_LOG_PATH":"must-not-be-used","WRANGLER_SEND_METRICS":"true"}
        self.runner=Mock(return_value=SimpleNamespace(returncode=0,stdout=json.dumps({"type":"oauth","token":TOKEN}).encode(),stderr=b""))
        self.options=dict(expected_node_sha256=subject._digest(self.node),expected_cli_sha256=subject._digest(self.cli),
                          expected_bundle_sha256=subject._digest(self.bundle),expected_version="4.151.1",
                          approved=True,runner=self.runner,environment=self.environment)

    def provider(self,**options):
        return subject.WranglerCredentialProvider(self.node,self.cli,**(self.options|options))

    def test_construction_and_unapproved_invocation_never_touch_files_or_auth(self):
        with patch.object(Path,"open",side_effect=AssertionError("NO_FILE_READ")):
            provider=self.provider(approved=False)
            with self.assertRaises(subject.CredentialUnavailable): provider()
        self.runner.assert_not_called()
        self.assertEqual(provider.process_attempts,0)
        with self.assertRaises(subject.CredentialUnavailable): self.provider(approved=1)()

    def test_fixed_command_child_only_settings_and_secret_not_emitted(self):
        before=dict(self.environment)
        before_files={p.relative_to(self.root) for p in self.root.rglob("*")}
        provider=self.provider()
        with redirect_stdout(io.StringIO()) as out,redirect_stderr(io.StringIO()) as err:
            token=provider()
        self.assertEqual(token,TOKEN)
        self.assertEqual(self.runner.call_count,1)
        args,kwargs=self.runner.call_args
        self.assertEqual(args[0],[str(self.node),str(self.cli),"auth","token","--json"])
        self.assertTrue(kwargs["capture_output"])
        self.assertIs(kwargs["shell"],False)
        self.assertIs(kwargs["check"],False)
        self.assertEqual(kwargs["stdin"],subprocess.DEVNULL)
        self.assertEqual(kwargs["timeout"],30)
        self.assertEqual(kwargs["cwd"],self.cli.parent.parent)
        for key,value in subject.CHILD_OVERRIDES.items(): self.assertEqual(kwargs["env"][key],value)
        self.assertNotIn("WRANGLER_LOG_PATH",kwargs["env"])
        self.assertEqual(self.environment,before)
        self.assertEqual({p.relative_to(self.root) for p in self.root.rglob("*")},before_files)
        self.assertEqual(out.getvalue()+err.getvalue(),"")
        self.assertNotIn(TOKEN,repr(provider))
        self.assertNotIn(TOKEN,str(args))

    def test_api_token_and_oauth_are_the_only_accepted_auth_kinds(self):
        for kind in ("api_token","oauth"):
            self.runner.return_value.stdout=json.dumps({"type":kind,"token":TOKEN}).encode()
            self.assertEqual(self.provider()(),TOKEN)

    def test_reuse_is_blocked_without_retry(self):
        provider=self.provider();provider()
        with self.assertRaises(subject.CredentialUnavailable): provider()
        self.assertEqual(self.runner.call_count,1)
        self.assertEqual(provider.process_attempts,1)

    def test_identity_tampering_blocks_before_process(self):
        for path in (self.node,self.cli,self.bundle):
            original=path.read_bytes();path.write_bytes(original+b"changed")
            with self.assertRaisesRegex(subject.CredentialUnavailable,"HASH_MISMATCH"): self.provider()()
            path.write_bytes(original)
        for key in ("expected_node_sha256","expected_cli_sha256","expected_bundle_sha256"):
            with self.assertRaises(subject.CredentialUnavailable): self.provider(**{key:"0"*64})()
        self.runner.assert_not_called()

    def test_version_and_reparse_paths_block_before_process(self):
        with self.assertRaisesRegex(subject.CredentialUnavailable,"VERSION_MISMATCH"):
            self.provider(expected_version="0.0.0")()
        with patch.object(subject,"_no_links",return_value=False):
            with self.assertRaisesRegex(subject.CredentialUnavailable,"FILES_INVALID"): self.provider()()
        fake=SimpleNamespace(parents=(),is_symlink=lambda:False,lstat=lambda:SimpleNamespace(st_file_attributes=0x400))
        self.assertFalse(subject._no_links(fake))
        self.runner.assert_not_called()

    def test_auth_endpoint_injection_and_global_keys_block_before_process(self):
        for key in subject.BLOCKED_ENV:
            with self.assertRaisesRegex(subject.CredentialUnavailable,"ENVIRONMENT_BLOCKED"):
                self.provider(environment={key:"not-allowed"})()
        with self.assertRaisesRegex(subject.CredentialUnavailable,"ENVIRONMENT_BLOCKED"):
            self.provider(environment={"wRaNgLeR_tOkEn_Url":"https://example.invalid"})()
        self.runner.assert_not_called()

    def test_environment_case_collisions_block_and_parent_is_not_changed(self):
        with self.assertRaisesRegex(subject.CredentialUnavailable,"ENVIRONMENT_INVALID"):
            self.provider(environment={"PATH":"one","Path":"two"})()
        environment={"wrangler_write_logs":"true","NODE_TLS_REJECT_UNAUTHORIZED":"0"}
        self.provider(environment=environment)()
        self.assertEqual(environment["wrangler_write_logs"],"true")
        self.assertEqual(self.runner.call_args.kwargs["env"]["WRANGLER_WRITE_LOGS"],"false")
        self.assertEqual(self.runner.call_args.kwargs["env"]["NODE_TLS_REJECT_UNAUTHORIZED"],"1")

    def test_malformed_output_never_exposes_credentials(self):
        payloads=[None,[],{}, {"type":"api_key","key":TOKEN,"email":"synthetic@example.invalid"},
                  {"type":"oauth","token":TOKEN,"extra":TOKEN}, {"type":"oauth","token":""},
                  {"type":"oauth","token":None}, {"type":"oauth","token":"bad\nvalue"},
                  {"type":"oauth","token":"bad value"}, {"type":"oauth","token":"非ASCII"},
                  {"type":"oauth","token":"x"*4097}]
        raws=[json.dumps(value).encode() for value in payloads]+[b"banner\n{}",b"\xff",b"x"*65537,
              b'{"type":"oauth","type":"api_token","token":"synthetic"}']
        for raw in raws:
            self.runner.return_value.stdout=raw
            with redirect_stdout(io.StringIO()) as out,redirect_stderr(io.StringIO()) as err:
                with self.assertRaises(subject.CredentialUnavailable) as caught: self.provider()()
            self.assertNotIn(TOKEN,str(caught.exception));self.assertEqual(out.getvalue()+err.getvalue(),"")

    def test_failure_timeout_and_exception_buffers_are_sanitized_without_retry(self):
        for error in (TimeoutError(TOKEN),RuntimeError(TOKEN),subject.CredentialUnavailable(TOKEN),
                      subprocess.TimeoutExpired(["synthetic"],30,output=TOKEN.encode(),stderr=TOKEN.encode())):
            runner=Mock(side_effect=error);provider=self.provider(runner=runner)
            with self.assertRaises(subject.CredentialUnavailable) as caught: provider()
            self.assertNotIn(TOKEN,str(caught.exception))
            with self.assertRaises(subject.CredentialUnavailable): provider()
            self.assertEqual(runner.call_count,1)
        self.runner.return_value.returncode=1
        self.runner.return_value.stderr=TOKEN.encode()
        with self.assertRaisesRegex(subject.CredentialUnavailable,"UNAVAILABLE"): self.provider()()

    def test_bad_output_types_and_oversized_stderr_are_rejected(self):
        for stdout,stderr in (("text",b""),(b"{}",None),(b"{}",b"x"*65537)):
            runner=Mock(return_value=SimpleNamespace(returncode=0,stdout=stdout,stderr=stderr))
            with self.assertRaises(subject.CredentialUnavailable): self.provider(runner=runner)()

    def test_d1_client_receives_token_in_memory_without_any_d1_request(self):
        opener=Mock(side_effect=AssertionError("NO_D1_REQUEST"))
        client=D1QueryClient("a"*32,"00000000-0000-0000-0000-000000000001",self.provider(),opener=opener)
        self.assertTrue(client.ready())
        self.assertEqual(client._token,TOKEN)
        client.clear();self.assertIsNone(client._token)
        opener.assert_not_called()

    def test_dry_run_and_missing_confirmation_never_invoke_auth(self):
        row={"public_id":"itm_"+"a"*24,"content_id":"synthetic-item"}
        runner=Mock(return_value=SimpleNamespace(stdout=json.dumps([{"success":True,"results":[row]}])))
        provider=self.provider()
        client=D1QueryClient("a"*32,"00000000-0000-0000-0000-000000000001",provider,opener=Mock())
        result=initial.run(public_ids=(row["public_id"],),runner=runner,query_client=client)
        self.assertEqual(result.status,"READY")
        self.assertEqual(provider.process_attempts,0);self.runner.assert_not_called()
        result=initial.run(public_ids=(row["public_id"],),execute=True,confirmed=False,query_client=client)
        self.assertEqual(result.status,"BLOCKED");self.runner.assert_not_called()


if __name__=="__main__": unittest.main()
