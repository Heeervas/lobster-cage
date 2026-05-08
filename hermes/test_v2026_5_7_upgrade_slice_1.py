import pathlib
import unittest


HERMES_DIR = pathlib.Path(__file__).parent
DOCKERFILE_PATH = HERMES_DIR / 'Dockerfile'
ENTRYPOINT_PATH = HERMES_DIR / 'entrypoint-wrapper.sh'
REMOVED_PATCH_PATH = HERMES_DIR / 'patches' / 'patch_post_tool_empty_retry.py'


def read_text(path: pathlib.Path) -> str:
    return path.read_text(encoding='utf-8')


class HermesV202657UpgradeSlice1Tests(unittest.TestCase):
    def test_uses_v2026_5_7_base_image(self):
        dockerfile = read_text(DOCKERFILE_PATH)

        self.assertIn('FROM nousresearch/hermes-agent:v2026.5.7', dockerfile)

    def test_dockerfile_does_not_wire_removed_post_tool_patch(self):
        dockerfile = read_text(DOCKERFILE_PATH)

        self.assertNotIn('patch_post_tool_empty_retry.py', dockerfile)

    def test_entrypoint_does_not_reapply_removed_post_tool_patch(self):
        entrypoint = read_text(ENTRYPOINT_PATH)

        self.assertNotIn('patch_post_tool_empty_retry.py', entrypoint)

    def test_removed_post_tool_patch_is_absent_from_local_patch_set(self):
        self.assertFalse(REMOVED_PATCH_PATH.exists())


if __name__ == '__main__':
    unittest.main()