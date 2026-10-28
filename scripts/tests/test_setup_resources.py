"""Resource bootstrap checks with stdlib mocks; no downloads or real media."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SCRIPTS))
import setup_resources as setup


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=SCRIPTS/"cache")
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.scripts=self.root/"scripts"
        (self.scripts/"config").mkdir(parents=True)
        self.model=b"synthetic model bytes"
        (self.scripts/"config/environment.json").write_text(json.dumps({
            "model_repo":"example/test-model",
            "model_sha256":hashlib.sha256(self.model).hexdigest().upper(),
        }),encoding="utf-8")
        self.patch=patch.object(setup,"SCRIPTS",self.scripts)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def run_setup(self,*args):
        with patch.object(sys,"argv",["setup_resources.py",*args]), contextlib.redirect_stdout(io.StringIO()):
            setup.main()

    def test_init_without_resources(self):
        self.run_setup("--init")
        for name in ["Inbox","raw","final","process","package","upload","scripts/vendor","scripts/models","scripts/fonts","scripts/cache"]:
            self.assertTrue((self.root/name).is_dir(),name)
        self.assertEqual(list((self.scripts/"vendor").iterdir()),[])

    def response(self,request,timeout):
        body=self.model if request.full_url.endswith("model.bin") else b"{}"
        response=io.BytesIO(body)
        response.headers={"content-length":str(len(body))}
        return response

    def test_model_download_and_reuse(self):
        with patch.object(setup,"urlopen",side_effect=self.response) as fetch, patch("video_pipeline.intake.doctor",return_value={"passed":True}):
            self.run_setup("--model")
            self.assertEqual(fetch.call_count,5)
            self.run_setup("--model")
            self.assertEqual(fetch.call_count,5)
        self.assertEqual((self.scripts/"models/large-v3-turbo/model.bin").read_bytes(),self.model)

    def test_bad_model_is_not_accepted(self):
        config=self.scripts/"config/environment.json"
        config.write_text(json.dumps({"model_repo":"example/test-model","model_sha256":"0"*64}),encoding="utf-8")
        with patch.object(setup,"urlopen",side_effect=self.response), self.assertRaisesRegex(ValueError,"checksum mismatch"):
            self.run_setup("--model")
        self.assertFalse((self.scripts/"models/large-v3-turbo/model.bin").exists())

    def test_package_install_uses_local_target_and_lock(self):
        with patch.object(setup.subprocess,"run") as install, patch("video_pipeline.intake.doctor",return_value={}):
            self.run_setup("--packages")
        command=install.call_args.args[0]
        self.assertEqual(command[command.index("--target")+1],str(self.scripts/"vendor"))
        self.assertEqual(command[command.index("-r")+1],str(self.scripts/"requirements.lock.txt"))

    def test_font_copy_refuses_overwrite(self):
        source=self.root/"licensed.ttf"
        source.write_bytes(b"\x00\x01\x00\x00synthetic font")
        with patch("video_pipeline.intake.doctor",return_value={}):
            self.run_setup("--font",str(source))
            self.run_setup("--font",str(source))
            source.write_bytes(b"\x00\x01\x00\x00different font")
            with self.assertRaisesRegex(ValueError,"Existing font differs"):
                self.run_setup("--font",str(source))
        self.assertEqual((self.scripts/"fonts/xinqingnian.ttf").read_bytes(),b"\x00\x01\x00\x00synthetic font")


if __name__=="__main__":
    (SCRIPTS/"cache").mkdir(parents=True,exist_ok=True)
    unittest.main()
